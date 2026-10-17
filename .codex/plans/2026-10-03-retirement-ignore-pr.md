Retirement inspection can inherit `core.excludesFile` and omit unique untracked
bytes. Pin it to `/dev/null` for every `Runtime.git` call. Renew the registered
module digest without changing publication behavior. Owner: #2741; review debt:
#2807. Regression: a real repository with an ambient exclude hiding a payload
reports the payload through Runtime after the correction.

Verification at e9cec5c77: 19 repository-retirement tests passed; all 12 scoped
cheap gates passed, including mypy, pinned Ruff, effector digest and writer
contract. `verify-scoped.sh` ended 75 because heavy verification admission was
denied for swap-fraction/vitals-shed. No heavy shard ran. The change remains
reviewable and published; completion/retirement is not certified until admitted
verification passes.
