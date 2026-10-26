# Data status

Written by `weekly_update.py` on 2026-10-26 16:35. Check here before an update to see whether a city has a new week.

| City | Newest week in the source | Newest forecast | In the app | New week to run? |
|---|---|---|---|---|
| Boston | Oct 18 - Oct 24 (BPHC CSVs in ~/GNN-Influenza-Boston/Data/BPHC Flu Data) | Oct 18 - Oct 24 | 2026-10-18 | no |
| Chicago | Oct 11 - Oct 17 (Chicago portal, posted Fri Oct 23 12:32 CT) | Oct 11 - Oct 17 | 2026-10-11 | no |

Weeks run Sunday to Saturday. Forecast folders, and `origin` in the app, are named by the start of the newest week they use: forecast 2026-10-18 uses data through Sat Oct 24 and forecasts the four weeks after it.

- Boston: BPHC has no feed. Download the dashboard CSVs into `~/GNN-Influenza-Boston/Data/BPHC Flu Data/`; the week shown above is the newest one in those files, not what BPHC has posted.
- Chicago: the City of Chicago portal (dataset 8vvr-jv2g) posts every Friday around 12:30 pm CT, adding the week that ended the Saturday before. So on a Friday the new week is the one that ended six days earlier, one week behind Boston's.
