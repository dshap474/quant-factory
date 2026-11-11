# example design space

Illustrative reference family, as of v002: a toy daily BTC direction signal built
from 30-day momentum. No version has run, so nothing here is evidence; the map shows the shape a
real family keeps. Each version's question and finding are in its `VERSION.toml`.

## Dimensions

**Locked:** current choice, tested against alternatives or fixed by rule. **Closed:** ruled out
at the tested settings. **Open:** uncertain or untested.

| Dimension | Status | Current choice or what was ruled out | Deciding versions |
| --- | --- | --- | --- |
| Input timing | locked (rule) | No shift; row T uses the close labeled T, which is known at T's close. | v001 |
| Momentum lookback | open (untested default) | 30 days; no other lookback compared. | v001 |
| Momentum sign | open | Sign of 30-day momentum vs a zero-information control; v001 NOT TESTED. | v001 |
| Volatility scaling | open | Sign times inverse 20-day realized volatility relative to its expanding mean, winsorized at ±3, vs the raw sign; preregistered, not run. | v002 |

## Open questions

| Question | Evidence so far | What would distinguish the explanations |
| --- | --- | --- |
| Does momentum sign carry next-day information at all, or only in calm regimes? | None; no version has run. | OOS IC of the raw sign split by realized-volatility regime, and the v002 scaled-vs-raw IC delta. |
