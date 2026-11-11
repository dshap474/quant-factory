# _example design space

Illustrative reference family, as of v002: a toy book that tilts an equal-weight control by
momentum. No version has run, so nothing here is evidence; the map shows the shape a real family
keeps. Each version's question and finding are in its `VERSION.toml`.

## Dimensions

**Locked:** current choice, tested against alternatives or fixed by rule. **Closed:** ruled out
at the tested settings. **Open:** uncertain or untested.

| Dimension | Status | Current choice or what was ruled out | Deciding versions |
| --- | --- | --- | --- |
| Control | locked (rule) | Equal-weight book; every version is judged against it. | v001 |
| Momentum tilt | open | Toy momentum tilt over the control; v001 preregistered, not run. | v001 |
| Volatility scaling | open | Tilt scaled by inverse realized volatility relative to the cross-sectional mean, vs the equal-weight control; preregistered, not run. | v002 |

## Open questions

| Question | Evidence so far | What would distinguish the explanations |
| --- | --- | --- |
| Does the tilt add anything over the control after costs? | None; no version has run. | The v002 Sharpe delta against the control, net of costs, out of sample. |
