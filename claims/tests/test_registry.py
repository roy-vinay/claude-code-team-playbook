import json
import multiprocessing
import os
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import Clock, git, make_repo, registry
from agentclaims.config import Config
from agentclaims.hook import evaluate
from agentclaims.mcp_server import Server
from agentclaims.registry import ClaimError, Registry
from agentclaims import diffcheck
from agentclaims.targets import Target

CALC = "src/pricing/calculate.py"
CLI = str(Path(__file__).resolve().parent.parent / "claims")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.clock = Clock()
        self.cfg, self.reg = registry(self.root, self.clock)

    def test_article_scenario(self):
        """Dana and Lee share calculate.py; a third claim overlaps Dana's."""
        a = self.reg.propose("CHK-412", "@dana", [f"{CALC}::calculate_total"])
        self.assertEqual(a.status, "accepted")
        b = self.reg.propose("PRM-207", "@lee", [f"{CALC}::apply_discount", "src/promotions/"])
        self.assertEqual(b.status, "accepted")
        self.clock.advance(13)
        c = self.reg.propose("PRM-207", "@lee", [f"{CALC}::calculate_total"], "store promo codes on the total")
        self.assertEqual(c.status, "pending")
        self.assertEqual(c.waiting_on[0]["to"], "@dana")
        self.assertIn("Do not edit", c.message)

        inbox = self.reg.inbox("@dana")
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["reason"], "store promo codes on the total")
        self.assertEqual(self.reg.inbox("@lee"), [])

        with self.assertRaises(ClaimError):
            self.reg.resolve(inbox[0]["id"], "@lee", True)  # can't approve your own request
        out = self.reg.resolve(inbox[0]["id"], "@dana", True, "go ahead, keep the signature")
        self.assertEqual(out["status"], "accepted")
        self.assertIn(Target.parse(f"{CALC}::calculate_total"), self.reg.held("PRM-207"))

    def test_decline_carries_the_note(self):
        self.reg.propose("CHK-412", "@dana", [f"{CALC}::calculate_total"])
        c = self.reg.propose("PRM-207", "@lee", [f"{CALC}::calculate_total"])
        req = self.reg.inbox("@dana")[0]
        self.reg.resolve(req["id"], "@dana", False, "I'll add promo_codes to Order by 3pm; wait for it")
        st = self.reg.status("PRM-207")[0]
        self.assertEqual(st["status"], "declined")
        self.assertIn("wait for it", st["note"])
        self.assertEqual(self.reg.held("PRM-207"), [])

    def test_codeowners_routing_and_team_membership(self):
        r = self.reg.propose("PRM-207", "@lee", ["src/checkout/cart.py"])
        self.assertEqual(r.status, "pending")
        self.assertEqual(r.waiting_on[0]["to"], "@shop/checkout")
        # Dana is on @shop/checkout, so the request lands in her inbox.
        self.assertEqual(len(self.reg.inbox("@dana")), 1)
        # Owners claiming their own code go straight through.
        self.assertEqual(self.reg.propose("CHK-412", "@dana", ["src/checkout/"]).status, "pending")  # overlaps Lee's pending claim

    def test_owner_claims_own_code(self):
        self.assertEqual(self.reg.propose("CHK-412", "@dana", ["src/checkout/"]).status, "accepted")

    def test_hot_file_rules(self):
        with self.assertRaises(ClaimError):
            self.reg.propose("X-1", "@sam", ["src/checkout/cart.py::cart"])  # not a hot file
        r = self.reg.propose("X-1", "@sam", [CALC])
        self.assertEqual(r.status, "pending")
        self.assertEqual(r.waiting_on[0]["to"], "@lead")
        self.assertEqual(r.waiting_on[0]["kind"], "hot-file")

    def test_same_ticket_can_extend_its_own_claim(self):
        self.reg.propose("CHK-412", "@dana", [f"{CALC}::calculate_total"])
        self.assertEqual(self.reg.propose("CHK-412", "@dana", [CALC.replace("calculate", "x")]).status, "accepted")

    def test_lease_expiry_and_renew(self):
        self.reg.propose("CHK-412", "@dana", [f"{CALC}::calculate_total"])
        self.clock.advance(239)
        self.assertEqual(self.reg.renew("CHK-412"), 1)
        self.clock.advance(239)
        self.assertTrue(self.reg.held("CHK-412"))
        self.clock.advance(2)
        self.assertEqual(self.reg.held("CHK-412"), [])
        # Expired claims stop blocking others.
        self.assertEqual(self.reg.propose("PRM-207", "@lee", [f"{CALC}::calculate_total"]).status, "accepted")
        ok, msg = self.reg.check_edit("CHK-412", CALC, {"calculate_total"})
        self.assertFalse(ok)

    def test_escalation_to_coordinator(self):
        self.reg.propose("CHK-412", "@dana", [f"{CALC}::calculate_total"])
        self.reg.propose("PRM-207", "@lee", [f"{CALC}::calculate_total"])
        self.assertEqual(self.reg.inbox("@lead"), [])
        self.clock.advance(61)
        self.reg.sweep()
        esc = self.reg.inbox("@lead")
        self.assertEqual(len(esc), 1)
        self.assertTrue(esc[0]["escalated"])
        self.assertEqual(self.reg.resolve(esc[0]["id"], "@lead", True)["status"], "accepted")

    def test_release(self):
        self.reg.propose("CHK-412", "@dana", ["src/checkout/"])
        self.assertEqual(self.reg.release("CHK-412"), 1)
        self.assertEqual(self.reg.propose("PRM-207", "@dana", ["src/checkout/"]).status, "accepted")

    def test_check_edit_function_level(self):
        self.reg.propose("PRM-207", "@lee", [f"{CALC}::apply_discount"])
        self.assertTrue(self.reg.check_edit("PRM-207", CALC, {"apply_discount"})[0])
        ok, msg = self.reg.check_edit("PRM-207", CALC, {"calculate_total"})
        self.assertFalse(ok)
        self.assertIn("calculate_total", msg)
        self.assertFalse(self.reg.check_edit("PRM-207", CALC, {"<module>"})[0])
        self.assertFalse(self.reg.check_edit("PRM-207", CALC, None)[0])


def _race(root, ticket, owner, q):
    os.environ.pop("CLAIMS_DB", None)
    reg = Registry(Config.load(root))
    q.put(reg.propose(ticket, owner, ["src/pricing/calculate.py::calculate_total"]).status)


class ConcurrencyTests(unittest.TestCase):
    def test_only_one_of_many_simultaneous_claims_wins(self):
        root = make_repo()
        Registry(Config.load(root))  # create schema
        q = multiprocessing.Queue()
        procs = [multiprocessing.Process(target=_race, args=(root, f"T-{i}", f"@dev{i}", q)) for i in range(8)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(30)
        results = sorted(q.get() for _ in procs)
        self.assertEqual(results.count("accepted"), 1, results)
        self.assertEqual(results.count("pending"), 7, results)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.cfg, self.reg = registry(self.root)
        os.environ["CLAIMS_TICKET"] = "PRM-207"

    def tearDown(self):
        os.environ.pop("CLAIMS_TICKET", None)

    def run_hook(self, tool, **inp):
        payload = {"tool_name": tool, "tool_input": inp, "cwd": str(self.root)}
        return evaluate(payload, self.cfg, self.reg)

    def test_blocks_then_allows(self):
        f = str(self.root / "src/promotions/codes.py")
        code, msg = self.run_hook("Edit", file_path=f, old_string="{}", new_string="{'X': 1}")
        self.assertEqual(code, 2)
        self.assertIn("claims propose src/promotions/codes.py", msg)
        self.reg.propose("PRM-207", "@lee", ["src/promotions/"])
        self.assertEqual(self.run_hook("Edit", file_path=f, old_string="{}", new_string="{'X': 1}")[0], 0)
        self.assertEqual(self.run_hook("Write", file_path=str(self.root / "src/promotions/new.py"), content="x=1")[0], 0)

    def test_hot_file_function_detection(self):
        self.reg.propose("PRM-207", "@lee", [f"{CALC}::apply_discount"])
        f = str(self.root / CALC)
        self.assertEqual(self.run_hook("Edit", file_path=f, old_string="return total\n",
                                       new_string="return total * 0.9\n")[0], 0)
        code, msg = self.run_hook("Edit", file_path=f, old_string="return subtotal * (1 + TAX_RATE)",
                                  new_string="return round(subtotal * (1 + TAX_RATE), 2)")
        self.assertEqual(code, 2)
        self.assertIn("calculate_total", msg)
        self.assertEqual(self.run_hook("Edit", file_path=f, old_string="0.08", new_string="0.09")[0], 2)
        self.assertEqual(self.run_hook("MultiEdit", file_path=f, edits=[
            {"old_string": "return total\n", "new_string": "return total - 1\n"}])[0], 0)

    def test_ignores_outside_repo_allowed_paths_and_other_tools(self):
        self.assertEqual(self.run_hook("Edit", file_path="/tmp/elsewhere.py", old_string="a", new_string="b")[0], 0)
        self.assertEqual(self.run_hook("Write", file_path=str(self.root / "specs/PRM-207.md"), content="spec")[0], 0)
        self.assertEqual(self.run_hook("Bash", command="ls")[0], 0)

    def test_no_ticket_blocks(self):
        os.environ.pop("CLAIMS_TICKET")
        code, msg = self.run_hook("Write", file_path=str(self.root / "src/x.py"), content="")
        self.assertEqual(code, 2)
        self.assertIn("/start", msg)

    def test_ticket_from_branch(self):
        os.environ.pop("CLAIMS_TICKET")
        git(self.root, "checkout", "-qb", "feat/PRM-207-promo-codes")
        self.reg.propose("PRM-207", "@lee", ["src/promotions/"])
        self.assertEqual(self.run_hook("Write", file_path=str(self.root / "src/promotions/a.py"), content="")[0], 0)


class DiffCheckTests(unittest.TestCase):
    def test_flags_changes_outside_claim(self):
        root = make_repo()
        cfg, reg = registry(root)
        git(root, "checkout", "-qb", "feat/PRM-207-promo")
        calc = root / CALC
        calc.write_text(calc.read_text().replace("return total", "return total * 0.9")
                        .replace("return subtotal * (1 + TAX_RATE)", "return round(subtotal * (1 + TAX_RATE), 2)"))
        (root / "src/promotions/codes.py").write_text("CODES = {'A': 1}\n")
        (root / "src/checkout/cart.py").write_text("def cart():\n    return [1]\n")
        git(root, "commit", "-qam", "work")
        targets = [Target.parse("src/promotions/"), Target.parse(f"{CALC}::apply_discount")]
        problems = diffcheck.check(cfg, "PRM-207", targets, "main")
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(any("calculate_total" in p for p in problems))
        self.assertTrue(any("src/checkout/cart.py" in p for p in problems))

        # The CLI with a manifest (the CI path) agrees and exits 1.
        manifest = root / ".claims/PRM-207.json"
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({"ticket": "PRM-207", "targets": [str(t) for t in targets]}))
        out = subprocess.run([sys.executable, CLI, "check-diff", "--base", "main", "--manifest", str(manifest)],
                             cwd=root, capture_output=True, text=True)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("calculate_total", out.stdout)


class McpTests(unittest.TestCase):
    def test_round_trip(self):
        root = make_repo()
        cfg = Config.load(root)
        server = Server(cfg)
        os.environ["CLAIMS_HANDLE"] = "@lee"
        try:
            init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2025-06-18"}})
            self.assertEqual(init["result"]["serverInfo"]["name"], "claims")
            self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
            tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
            self.assertIn("claims_propose", [t["name"] for t in tools])
            res = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "claims_propose", "arguments": {"ticket": "PRM-207", "targets": ["src/promotions/"]}}})
            self.assertEqual(json.loads(res["result"]["content"][0]["text"])["status"], "accepted")
            bad = server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "claims_propose", "arguments": {"ticket": "PRM-207", "targets": ["src/checkout/cart.py::x"]}}})
            self.assertTrue(bad["result"]["isError"])
        finally:
            os.environ.pop("CLAIMS_HANDLE", None)

    def test_stdio_process(self):
        root = make_repo()
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "claims_status", "arguments": {"all": True}}},
        ]
        out = subprocess.run([sys.executable, CLI, "mcp"], cwd=root, capture_output=True, text=True,
                             input="\n".join(json.dumps(m) for m in msgs) + "\n")
        lines = [json.loads(line) for line in out.stdout.splitlines()]
        self.assertEqual([m["id"] for m in lines], [1, 2])
        self.assertEqual(json.loads(lines[1]["result"]["content"][0]["text"]), [])


if __name__ == "__main__":
    unittest.main()
