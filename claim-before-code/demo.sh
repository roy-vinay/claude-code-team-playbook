#!/bin/sh
# Replays the scenario from the article in a throwaway repo:
# Dana (checkout) and Lee (promotions) both work in src/pricing/calculate.py.
set -e
CBC="$(cd "$(dirname "$0")" && pwd)/cbc"
DEMO=$(mktemp -d)
cd "$DEMO"
git init -q -b main
git config user.email demo@example.com
git config user.name Demo

mkdir -p src/pricing src/promotions src/checkout .github
cat > src/pricing/calculate.py <<'EOF'
TAX_RATE = 0.08


def calculate_total(order):
    subtotal = sum(i.price for i in order.items)
    return subtotal * (1 + TAX_RATE)


def apply_discount(total, code):
    return total
EOF
echo "CODES = {}" > src/promotions/codes.py
cat > .github/CODEOWNERS <<'EOF'
/src/checkout/    @dana
/src/promotions/  @lee
EOF
cat > .cbc.toml <<'EOF'
coordinator = "@lead"
hot_files = ["src/pricing/calculate.py"]
EOF
git add -A && git commit -qm init

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
hook() { # $1 ticket, $2 old, $3 new
  printf '{"tool_name":"Edit","cwd":"%s","tool_input":{"file_path":"%s/src/pricing/calculate.py","old_string":"%s","new_string":"%s"}}' \
    "$DEMO" "$DEMO" "$2" "$3" | CBC_TICKET="$1" "$CBC" hook && echo "hook: edit allowed" || echo "hook: edit blocked (exit 2)"
}

step "10:02  Dana's checkout agent claims calculate_total"
CBC_HANDLE=@dana "$CBC" propose --ticket CHK-412 "src/pricing/calculate.py::calculate_total"

step "10:15  Lee's promotions agent claims apply_discount in the same file, plus its own folder"
CBC_HANDLE=@lee "$CBC" propose --ticket PRM-207 "src/pricing/calculate.py::apply_discount" src/promotions/

step "Lee's agent edits apply_discount: inside its claim"
hook PRM-207 "return total\\n" "return total * 0.9\\n"

step "10:28  Lee's agent finds it also needs calculate_total and tries to edit it directly"
hook PRM-207 "return subtotal * (1 + TAX_RATE)" "return round(subtotal * (1 + TAX_RATE), 2)"

step "So it asks instead"
CBC_HANDLE=@lee "$CBC" propose --ticket PRM-207 --reason "store applied promo codes on the total" \
  "src/pricing/calculate.py::calculate_total" || true

step "Dana's inbox"
CBC_HANDLE=@dana "$CBC" inbox

step "Dana declines and says what to do instead"
REQ=$(CBC_HANDLE=@dana "$CBC" --json inbox | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
CBC_HANDLE=@dana "$CBC" decline "$REQ" --note "I'll add a promo_codes argument to calculate_total by 3pm. Build against that."

step "What Lee's agent sees"
"$CBC" status --ticket PRM-207

step "Activity feed"
"$CBC" feed

echo
echo "Demo repo left at $DEMO"
