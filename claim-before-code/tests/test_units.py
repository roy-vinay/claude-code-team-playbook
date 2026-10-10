import textwrap
import unittest

from helpers import CALCULATE  # noqa: F401  (sets sys.path)
from claim_before_code.codeowners import CodeOwners
from claim_before_code.functions import changed_functions
from claim_before_code.targets import MODULE, Target, covers, overlaps


class TargetTests(unittest.TestCase):
    def t(self, s):
        return Target.parse(s)

    def test_parse_normalizes(self):
        self.assertEqual(str(self.t("./src/a.py")), "src/a.py")
        self.assertEqual(str(self.t("/src/a.py :: f")), "src/a.py::f")
        with self.assertRaises(ValueError):
            self.t("src/::f")

    def test_overlaps(self):
        self.assertTrue(overlaps(self.t("src/"), self.t("src/a.py")))
        self.assertTrue(overlaps(self.t("src/a.py"), self.t("src/a.py::f")))
        self.assertFalse(overlaps(self.t("src/a.py::f"), self.t("src/a.py::g")))
        self.assertTrue(overlaps(self.t("src/a.py::Order"), self.t("src/a.py::Order.total")))
        self.assertFalse(overlaps(self.t("src/a/"), self.t("src/ab/")))
        self.assertFalse(overlaps(self.t("src/a.py"), self.t("src/b.py")))

    def test_covers(self):
        self.assertTrue(covers(self.t("src/"), "src/x/y.py"))
        self.assertTrue(covers(self.t("src/a.py::f"), "src/a.py", "f"))
        self.assertFalse(covers(self.t("src/a.py::f"), "src/a.py", "g"))
        self.assertFalse(covers(self.t("src/a.py::f"), "src/a.py", MODULE))
        self.assertFalse(covers(self.t("src/a.py::f"), "src/a.py"))


class CodeOwnersTests(unittest.TestCase):
    def test_last_match_wins_and_patterns(self):
        co = CodeOwners.parse(textwrap.dedent("""\
            *            @everyone
            /src/        @core
            *.md         @docs
            /src/pricing/ @pricing   # pricing team
            docs/**/api  @api
            """))
        self.assertEqual(co.owners("README.md"), ["@docs"])
        self.assertEqual(co.owners("src/app.py"), ["@core"])
        self.assertEqual(co.owners("src/pricing/calculate.py"), ["@pricing"])
        self.assertEqual(co.owners("src/pricing/"), ["@pricing"])
        self.assertEqual(co.owners("docs/v1/api/x.txt"), ["@api"])
        self.assertEqual(co.owners("lib/x.go"), ["@everyone"])


class FunctionTests(unittest.TestCase):
    def test_python_single_function(self):
        new = CALCULATE.replace("return total", "return total * 0.9")
        self.assertEqual(changed_functions("p.py", CALCULATE, new), {"apply_discount"})

    def test_python_module_level(self):
        new = CALCULATE.replace("0.08", "0.09")
        self.assertEqual(changed_functions("p.py", CALCULATE, new), {MODULE})

    def test_python_new_function(self):
        new = CALCULATE + "\n\ndef promo_codes():\n    return []\n"
        self.assertEqual(changed_functions("p.py", CALCULATE, new), {"promo_codes"})

    def test_python_method(self):
        old = "class Order:\n    x = 1\n\n    def total(self):\n        return 1\n\n    def tax(self):\n        return 0\n"
        new = old.replace("return 1", "return 2")
        self.assertEqual(changed_functions("o.py", old, new), {"Order.total"})
        self.assertEqual(changed_functions("o.py", old, old.replace("x = 1", "x = 2")), {"Order"})

    def test_js_functions(self):
        old = textwrap.dedent("""\
            import x from 'y';
            export function calculateTotal(order) {
              const f = () => { return 1; };
              return order.items.reduce((a, i) => a + i.price, 0);
            }
            export const applyDiscount = async (total, code) => {
              return total;
            };
            const double = n => n * 2;
            """)
        new = old.replace("return total;", "return total * 0.9;")
        self.assertEqual(changed_functions("p.ts", old, new), {"applyDiscount"})
        self.assertEqual(changed_functions("p.ts", old, old.replace("n * 2", "n * 3")), {"double"})
        self.assertEqual(changed_functions("p.ts", old, old.replace("'y'", "'z'")), {MODULE})

    def test_unsupported_language(self):
        self.assertIsNone(changed_functions("a.go", "package a\n", "package b\n"))


if __name__ == "__main__":
    unittest.main()
