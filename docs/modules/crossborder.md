# crossborder — MX/US residency, treaty, FBAR and FEIE-vs-FTC

Mounted at `/api/crossborder`. Rules and constants: [rules-us.md](rules-us.md).

**Everything here is informational and Aurum decides nothing.** Residency, a treaty position, an FBAR
obligation and the FEIE/FTC choice all turn on facts Aurum cannot see. The output is a set of flags
that say *what to look into, and with whom* — never what to do. Every response carries the disclaimer
and every section carries its rule's explain with citations.

## Files

```
aurum/crossborder/
  profile.py     CrossBorderProfile (pydantic v2, validated) + load/store on the workspace
  assessment.py  composes the four xb.* rules into sections + flags
  router.py      the endpoints
```

## The profile

Stored at `workspace.profile["crossborder"]`, so it travels with the workspace JSON and is masked by
`Workspace.masked()` like the rest of the profile.

| field | type | notes |
|---|---|---|
| `days_mx`, `days_us`, `days_us_prior_1`, `days_us_prior_2`, `days_abroad_for_feie` | int 0–366 | rejected outside the range |
| `home_mx`, `home_us`, `green_card`, `bona_fide_resident_abroad` | bool | |
| `citizenship` | list[str] | upper-cased |
| `filing_status` | `single\|mfj\|mfs\|hoh` | |
| `main_professional_center`, `treaty_permanent_home`, `treaty_center_of_vital_interests`, `treaty_habitual_abode`, `treaty_nationality` | `MX\|US\|null` | anything else is a 422 |
| `mx_source_income_share` | Decimal 0–1 or null | the CFF art. 9 centre-of-vital-interests test |
| `foreign_tax_paid_usd` | Decimal | the FTC side of the comparison |
| `income_sources` | `[{country, kind, amount, currency}]` | non-US USD sources are the § 911 base |
| `foreign_accounts` | `[{country, institution?, max_balance_usd}]` | highest balance at any point in the year |

Floats are refused everywhere money appears (money is `Decimal`, see
[ARCHITECTURE.md](../ARCHITECTURE.md#principles)).

## Endpoints

- `PUT /api/crossborder/{ws}/profile` — validate and store. 404 on an unknown workspace, 422 on bad input.
- `GET /api/crossborder/{ws}/profile` — read it back. 404 when none has been stored.
- `GET /api/crossborder/{ws}/assessment` — the composed assessment. 404 (with a "PUT one first" message)
  when the workspace has no profile.

```json
{"workspace":"demo-us",
 "residency":{"mx":true,"us":true,"dual":true,
              "weighted_us_days":{"amount":"225.00","currency":"DAY"},"explain":{}},
 "treaty":{"applies":true,"resolved_at_step":2,"checklist":[{"step":1,"key":"permanent_home","label":"…"}],"explain":{}},
 "fbar":{"required":true,"aggregate":{"amount":"16700.00","currency":"USD"},"threshold":"10000","explain":{}},
 "feie_vs_ftc":{"options":[{"option":"FEIE","citation":"IRC 911","value":{}},
                           {"option":"FTC","citation":"IRC 901","value":{}}],"explain":{}},
 "flags":["FBAR likely required — …","Possible dual residency — treaty tie-breaker: …","FEIE vs FTC — explore with a preparer: …"],
 "unverified_constants":["xb.mx.residency_cff9","xb.treaty.article_4","…"],
 "disclaimer":"Informational only. … Aurum decides nothing."}
```

Both endpoints write an `aurum.core.audit` row; the assessment records the rule versions used.

## Flags

| condition | flag |
|---|---|
| aggregate foreign balance > USD 10,000 and the person is a US person | *FBAR likely required* |
| accounts held but under the threshold | reminder that the test is the highest balance on any single day |
| resident under both tests | *Possible dual residency — treaty tie-breaker …* (needs Form 8833) |
| resident under exactly one | which country's worldwide-income duty applies |
| neither | "that is unusual; confirm the day counts and where your home is" |
| § 911 exclusion available | *FEIE vs FTC — explore with a preparer …* with both amounts |
| foreign earned income but neither § 911 test met | the same flag, pointing at the credit instead |
| US person with zero US days | living abroad does not end a citizen's filing obligation |
| US person with no accounts recorded | add them; FBAR is easy to trip over |

Flag wording is asserted in the tests, because the wording *is* the product here.

## Caveats

`xb.mx.residency_cff9` and `xb.treaty.article_4` are **(verify)**: CFF art. 9 and the treaty text were
not read in a primary source in the 2026-09-06 pass, so the Mexican-residency logic and the tie-breaker
ordering (which follows the OECD model) both surface `(verify)` in their explains and appear in
`unverified_constants`. A day count in Mexico is treated as a *signal* only — CFF art. 9 turns on the
home and the centre of vital interests, not on 183 days.

Not modelled: Form 8938/FATCA thresholds, § 904 baskets and carryovers, the closer-connection exception
beyond a flag, totalization (there is no US–MX agreement in force — `(verify)`), state residency, and
the Mexican side of any treaty claim.

## Tests

`tests/crossborder/test_crossborder_api.py` — profile round-trip through the workspace file, four
validation rejections, 404s, the full composed assessment with its flags, the FBAR boundary at exactly
USD 10,000, a non-US person, the `demo-us` dual-residency case, and the unverified-constants list.
