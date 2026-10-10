import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from claim_before_code.config import Config  # noqa: E402
from claim_before_code.registry import Registry  # noqa: E402

CALCULATE = textwrap.dedent('''\
    TAX_RATE = 0.08


    def calculate_total(order):
        subtotal = sum(i.price for i in order.items)
        return subtotal * (1 + TAX_RATE)


    def apply_discount(total, code):
        return total
    ''')

CONFIG = textwrap.dedent('''\
    coordinator = "@lead"
    response_window_minutes = 60
    lease_minutes = 240
    hot_files = ["src/pricing/calculate.py", "src/models/order.py"]

    [teams]
    "@shop/checkout" = ["@dana"]
    "@shop/promotions" = ["@lee"]
    ''')

CODEOWNERS = textwrap.dedent('''\
    /src/checkout/    @shop/checkout
    /src/promotions/  @shop/promotions
    /src/inventory/   @sam
    ''')


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, minutes):
        self.t += minutes * 60


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def make_repo(config=CONFIG, codeowners=CODEOWNERS):
    tmp = Path(tempfile.mkdtemp(prefix="cbc-test-"))
    git(tmp, "init", "-q", "-b", "main")
    git(tmp, "config", "user.email", "test@example.com")
    git(tmp, "config", "user.name", "Test")
    (tmp / "src/pricing").mkdir(parents=True)
    (tmp / "src/checkout").mkdir(parents=True)
    (tmp / "src/promotions").mkdir(parents=True)
    (tmp / "src/pricing/calculate.py").write_text(CALCULATE)
    (tmp / "src/checkout/cart.py").write_text("def cart():\n    return []\n")
    (tmp / "src/promotions/codes.py").write_text("CODES = {}\n")
    (tmp / "README.md").write_text("demo\n")
    if config:
        (tmp / ".cbc.toml").write_text(config)
    if codeowners:
        (tmp / ".github").mkdir()
        (tmp / ".github/CODEOWNERS").write_text(codeowners)
    git(tmp, "add", "-A")
    git(tmp, "commit", "-qm", "init")
    return tmp


def registry(root, clock=None):
    os.environ.pop("CBC_DB", None)
    cfg = Config.load(root)
    return cfg, Registry(cfg, now=clock or Clock())
