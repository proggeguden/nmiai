# Manual Submission Tests — Round 38

Key changes:
- thinking_level="low" on all LLMs (was "high" default → 60-180s wasted)
- PDF text extraction via pymupdf (no more relying on Gemini to parse PDFs)
- filter_data instant Python tool (replaces analyze_response for sorting/filtering)
- Dimension value split (no bulk POST)
- Account 1500 needs customer ref
- Language preservation (don't translate field values)
- Payment suffix auto-add on PUT /invoice

Submit ONE at a time, wait for score, then submit next.

---

# SUBMISSION 1

## PROMPT
Voce recebeu uma fatura de fornecedor (ver PDF anexo). Registe a fatura no Tripletex. Crie o fornecedor se nao existir. Use a conta de despesas correta e o IVA de entrada.

### FILE
files/leverandorfaktura_pt_02.pdf

## SCORE
2/10

## NOTES
Fails on Register incoming supplier invoice. Is the correct data being used and the correct endpoints? And since it fails fast, is there more that should be done? Should we not fail fast anymore? We removed it for a reason.

---

# SUBMISSION 2

## PROMPT
Utfør forenklet årsoppgjør for 2025: 1) Beregn og bokfør årlige avskrivninger for tre eiendeler: IT-utstyr (108700 kr, 5 år lineært, konto 1210), Kontormaskiner (238150 kr, 6 år, konto 1200), Kjøretøy (92450 kr, 5 år, konto 1230). Bruk konto 6010 for avskrivningskostnad og 1209 for akkumulerte avskrivninger. 2) Reverser forskuddsbetalte kostnader (totalt 53150 kr på konto 1700). 3) Beregn og bokfør skattekostnad (22 % av skattbart resultat) på konto 8700/2920. Bokfør hver avskrivning som et eget bilag.

## SCORE
6/10

## NOTES
A lot of 'Placeholder $step_2.id references an empty search result (step 2)'. Is this a new bug in our code?

---

# SUBMISSION 3

## PROMPT
Concilia el extracto bancario (CSV adjunto) con las facturas abiertas en Tripletex. Relaciona los pagos entrantes con las facturas de clientes y los pagos salientes con las facturas de proveedores. Maneja los pagos parciales correctamente.

### FILE
files/bankutskrift_es_06.csv

## SCORE
0/10

## NOTES
Are we handling csv files properly?? Is any data from the file being used?

---

# SUBMISSION 4

## PROMPT
We have discovered errors in the general ledger for January and February 2026. Review all vouchers and find the 4 errors: a posting to the wrong account (account 7300 used instead of 7000, amount 2000 NOK), a duplicate voucher (account 6590, amount 3400 NOK), a missing VAT line (account 6590, amount excl. 13150 NOK missing VAT on account 2710), and an incorrect amount (account 6500, 8050 NOK posted instead of 6950 NOK). Correct all errors with appropriate correction vouchers.

## SCORE
7.5/10

## NOTES
No API error, but something going wrong. Check the dataflow between the endpoints! What are we missing?

---

# SUBMISSION 5

## PROMPT
Opprett ein ordre for kunden Skogheim AS (org.nr 865101422) med produkta Opplæring (2677) til 15100 kr og Webdesign (5844) til 20600 kr. Konverter ordren til faktura og registrer full betaling.

## SCORE
8/8

## NOTES


---



---

# SUBMISSION 6

## PROMPT
Recebemos a fatura INV-2026-7230 do fornecedor Solmar Lda (org. nº 973188410) no valor de 7700 NOK com IVA incluído. O montante refere-se a serviços de escritório (conta 7140). Registe a fatura do fornecedor com o IVA dedutível correto (25 %).

## SCORE
0/8

## NOTES
POST /incomingInvoice → 422
response: "{"status":422,"code":18000,"message":"Validering feilet.","link":"https://tripletex.no/v2-docs/","developerMessage":null,"validationMessages":[{"field":"orderLines.externalId","message":"Kan ikke være null.","path":"orderLines[0].externalId","rootId":null}],"requestId":"a01e0d58-15f8-435c-9fea-9ab4e5b0767f"}"

---


---

# SUBMISSION 7

## PROMPT
Sie haben einen Arbeitsvertrag erhalten (siehe beigefugte PDF). Erstellen Sie den Mitarbeiter in Tripletex mit allen Details aus dem Vertrag: Personalnummer, Geburtsdatum, Abteilung, Berufsschluessel, Gehalt, Beschaeftigungsprozentsatz und Startdatum.

### FILE
files/arbeidskontrakt_de_07.pdf

## SCORE
10/22

## NOTES
POST /division → 422
Still not extracting data

---

---

# SUBMISSION 8

## PROMPT
Vous avez recu une lettre d'offre (voir PDF ci-joint) pour un nouvel employe. Effectuez l'integration complete : creez l'employe, attribuez le bon departement, configurez les details d'emploi avec le pourcentage et le salaire annuel, et configurez les heures de travail standard.

### FILE
files/tilbudsbrev_fr_07.pdf

## SCORE
5/14

## NOTES
Kind of similar errors as the one over I think.

---


---

# SUBMISSION 9

## PROMPT


## SCORE


## NOTES


---
