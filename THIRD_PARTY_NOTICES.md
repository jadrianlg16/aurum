# Third-party notices

Aurum's own code is covered by the notice in the [README](README.md#license). This file lists material
in the repository that comes from, or is adapted from, third parties. Installed dependencies (Python
and npm packages) keep their own licenses; they are listed with their declared licenses in
[`docs/LICENSES.md`](docs/LICENSES.md), and none of them is vendored into this repository.

## Icon paths

Several stroke icons in [`web-ui/src/components/ui/Icon.tsx`](web-ui/src/components/ui/Icon.tsx)
(for example `list`, `alert`, `clip`, `layers`, `sun`, `more`) follow or simplify the shapes of the
Feather and Lucide icon sets on the same 24-unit grid. Those sets are distributed under the licenses
below.

**Feather** — <https://github.com/feathericons/feather>

```text
The MIT License (MIT)

Copyright (c) 2013-2023 Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**Lucide** — <https://github.com/lucide-icons/lucide>

```text
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of
Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

## Tax tables, rates and statute excerpts

Rates, thresholds and tables in `aurum/rules/`, and the short statute excerpts quoted in rule
explanations, come from official government publications; the rules cite each one with its source
and the date it was read:

- Mexico: Ley del Impuesto sobre la Renta, Ley del IVA, Código Fiscal de la Federación, Ley del
  Seguro Social, Ley del INFONAVIT (Cámara de Diputados), the Resolución Miscelánea Fiscal 2026 and
  its Anexo 8 (SAT / Diario Oficial de la Federación), and the Ley de Hacienda del Estado de Nuevo
  León (Periódico Oficial del Estado).
- United States: Internal Revenue Code (Title 26 U.S.C.), Treasury Regulations, IRS Revenue Procedure
  2025-32 and IRS publications, 31 CFR 1010.350, the Texas Tax Code and Texas Comptroller guidance.
- The US–Mexico income tax treaty.

Mexican laws and official acts are excluded from copyright protection (Ley Federal del Derecho de
Autor, art. 14, fr. VIII), and works of the US federal government are not subject to copyright
(17 U.S.C. § 105).

The law texts in `tests/fixtures/law/` are not official excerpts: they are short synthetic
paraphrases written for the tests, modelled on the provisions above, so the retrieval tests and the
eval have something realistic to search.

## Fonts

No font files are bundled. The UI uses each platform's system font stack.

## Models

No model weights are included. The default models are downloaded by the user through Ollama and
keep their own licenses: `llama3.1:8b` (Llama 3.1 Community License) and `nomic-embed-text`
(Apache-2.0).
