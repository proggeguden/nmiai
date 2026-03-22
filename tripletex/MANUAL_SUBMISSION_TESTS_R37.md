# Manual Submission Tests — Round 37 (revision tripletex-00066-zlw)

Logs filter: `resource.labels.revision_name="tripletex-00066-zlw"`

Key changes in this round:
- Supplier invoice: POST /incomingInvoice?sendTo=ledger (was /ledger/voucher)
- analyze_response REMOVED — planner computes math, API handles sorting/filtering
- Single accountant persona (no more random persona selection)
- Missing accounts: GET then POST if empty
- All dead code removed

Submit ONE at a time, wait for score, then submit next.

---

# SUBMISSION 1

## PROMPT
Erfassen Sie 18 Stunden für Mia Meyer (mia.meyer@example.org) auf der Aktivität "Testing" im Projekt "Sicherheitsaudit" für Nordlicht GmbH (Org.-Nr. 934651995). Stundensatz: 1400 NOK/h. Erstellen Sie eine Projektrechnung an den Kunden basierend auf den erfassten Stunden.

## SCORE
8/8

## NOTES
One 422 error, maybe we can get a better score. Look long at the logs, request and response bodys to see if data flows correctly. We should also research the tripletex API specs to figure out if the ensure_bank_account validation is necessary, or if there is something we are missing here. But I got more points when this was solved, so something is correct here!

---

# SUBMISSION 2

## PROMPT
Nous avons envoyé une facture de 11764 EUR à Forêt SARL (nº org. 832101389) lorsque le taux de change était de 10.90 NOK/EUR. Le client a maintenant payé, mais le taux est de 11.19 NOK/EUR. Enregistrez le paiement et comptabilisez l'écart de change (agio) sur le bon compte.

## SCORE
2/10

## NOTES
405  Method Not Allowed on PUT /invoice/2147673222. Research tripletex API specs. Also, always check if the data flow between requests looks correct and is not missing. Check the jsonPayload -> params for request parameters and jsonPayload -> response for the response.

---

# SUBMISSION 3

## PROMPT
Defina um preço fixo de 420900 NOK no projeto "Implementação ERP" para Horizonte Lda (org. nº 976946081). O gestor de projeto é Rafael Santos (rafael.santos@example.org). Fature ao cliente 33 % do preço fixo como pagamento por etapa.

## SCORE
6/8

## NOTES
unresolved refs errors for two steps, look at the logs. Also, always check if the data flow between requests looks correct and is not missing.

---

# SUBMISSION 4

## PROMPT
Vi trenger Whiteboard fra denne kvitteringen bokfort pa avdeling Lager. Bruk riktig utgiftskonto basert pa kjopet, og sorg for korrekt MVA-behandling.

### FILE ATTACHMENT
files/kvittering_nb_04.pdf

## SCORE
0/10

## NOTES
Many 422 errors and also no points. The solution here must be pretty wrong. Look at the steps, the data flow etc. Is it still not getting data from the PDF? It should be possible to understand from the PDF what parameters should be linked and add the correct ones. 

---

# SUBMISSION 5

## PROMPT
Enviamos una factura por 5230 EUR a Río Verde SL (org. nº 875655612) cuando el tipo de cambio era 11.95 NOK/EUR. El cliente ha pagado ahora, pero el tipo es 12.20 NOK/EUR. Registre el pago y contabilice la diferencia de tipo de cambio (agio) en la cuenta correcta.

## SCORE
5/10

## NOTES
No API errors. But something in the dataflow, or the usage of wrong endpoints, must be the case. Check if the data flow between requests looks correct and is not missing. Check the jsonPayload -> params for request parameters and jsonPayload -> response for the response.

---
