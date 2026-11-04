# Partner feed URL update (draft)

Subject: Joinrs job XML feeds — new country endpoints (full descriptions)

Hi,

We have updated the Joinrs XML feed endpoints. Feeds are now split by country/region so each file stays manageable, and **job descriptions are complete** (no truncation).

Base: `https://lw.joinrs.com/wrapping/`

Replace `{platform}` with `jooble`, `talent`, or `adzuna`.

| Feed | URL |
| --- | --- |
| Italy (priority 1–4) | `…/{platform}/it` |
| Italy (priority 5) | `…/{platform}/it5` |
| Spain | `…/{platform}/es` |
| USA (shard 1–5) | `…/{platform}/us/1` … `…/{platform}/us/5` |
| UK | `…/{platform}/uk` |
| France | `…/{platform}/fr` |
| Germany | `…/{platform}/de` |
| Rest of Europe (+ PT, BE) | `…/{platform}/eu` |
| Americas (CA, BR, LATAM) | `…/{platform}/americas` |
| Asia | `…/{platform}/asia` |
| Rest of world | `…/{platform}/row` |

**Removed / replaced:** bare `/{platform}` root (use `/it` + `/it5`), `/us` (single), `/eu3`, and the old combined Italy+Spain root semantics.

Please update your integration to the URLs above. Contact us if you need help choosing shards for USA.

Thanks,
Joinrs
