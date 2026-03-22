# Manual Submission Tests — Round 37e (revision tripletex-00067-pqw)

Logs filter: `resource.labels.revision_name="tripletex-00067-pqw"`

Key changes:
- POST /incomingInvoice for supplier invoices (was /ledger/voucher → 0 pts)
- analyze_response REMOVED — planner computes math, API handles sorting
- Single accountant persona, NEVER GUESS data, always look up from Tripletex
- Intent-based entity handling (no more GET→POST duplicates)
- Division always created for employment chain
- /:payment auto-added when missing on PUT /invoice
- 303 lines dead code removed

Submit ONE at a time, wait for score, then submit next.

---

# SUBMISSION 1

## PROMPT
L'un de vos clients a une facture en retard. Trouvez la facture en retard et enregistrez des frais de rappel de 35 NOK. Debit creances clients (1500), credit revenus de rappel (3400). Créez également une facture pour les frais de rappel au client et envoyez-la. De plus, enregistrez un paiement partiel de 5000 NOK sur la facture en retard.

## SCORE
7/10

## NOTES
One 422 error. Started writing the steps in the language of the prompt haha. Maybe the prompt should be translated to accountant English for better performance, what do you think? Look into the dataflow, if request and response bodys are flowing correctly, and why an error occurs. 

---

# SUBMISSION 2

## PROMPT
Total costs increased significantly from January to February 2026. Analyze the general ledger and identify the three expense accounts with the largest increase in amount. Create an internal project for each of the three accounts using the account name. Also create an activity for each project.

## SCORE
4/8

## NOTES
No API errors. Must investigate if the correct data is used. 

---

# SUBMISSION 3

## PROMPT
Crea el producto "Informe de análisis" con número de producto 6859. El precio es 34700 NOK sin IVA, utilizando la tasa estándar del 25 %.

## SCORE
7/7 

## NOTES
Postes product successfully!

---

# SUBMISSION 4

## PROMPT
Sie haben ein Angebotsschreiben erhalten (siehe beigefugte PDF) fuer einen neuen Mitarbeiter. Fuehren Sie das vollstaendige Onboarding durch: erstellen Sie den Mitarbeiter, weisen Sie die richtige Abteilung zu, richten Sie die Beschaeftigungsdetails mit Prozentsatz und Jahresgehalt ein, und konfigurieren Sie die Standardarbeitszeit.

### FILE ATTACHMENT
files/tilbudsbrev_de_08.pdf

## SCORE
0/14

## NOTES
Another task with a file that fails drastically. Here a lot of weird things are going on. We need to investigate the content of the PDF. It is handled really poorly. I bet most of the information needed is in the PDF. What is it doing now, trying to create hallucinated divisions? This must be fixed. Errors here also lead to unresolved refs errors...

---

# SUBMISSION 5

## PROMPT
Opprett ein fri rekneskapsdimensjon "Region" med verdiane "Midt-Norge" og "Vestlandet". Bokfør deretter eit bilag på konto 7140 for 43750 kr, knytt til dimensjonsverdien "Midt-Norge".

## SCORE
2/13

## NOTES
Look thoroughly through the logs. Something wrong with how the intent of the prompt is understood. 

---

---

# SUBMISSION 6

## PROMPT
Le client Cascade SARL (nº org. 862852745) a réclamé concernant la facture pour "Développement système" (15200 NOK HT). Émettez un avoir complet qui annule l'intégralité de la facture.

## SCORE
Timeout

## NOTES
Are we missing endpoint knowledge for credit notes for invoices? The planner used a really long time.

---
