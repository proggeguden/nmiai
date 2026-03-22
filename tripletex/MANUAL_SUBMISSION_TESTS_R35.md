# Manual Submission Tests — Round 35 (revision tripletex-00063-cup)

Logs filter: `resource.labels.revision_name="tripletex-00063-cup"`

Submit ONE at a time, wait for score, then submit next. This keeps logs sequential and easy to trace.

---

# SUBMISSION 1

## PROMPT
Créez et envoyez une facture au client Étoile SARL (nº org. 976414284) de 20000 NOK hors TVA. La facture concerne Heures de conseil.

## SCORE
6/7

## NOTES
404 error from 'step 6: Send the invoice'.

---

# SUBMISSION 2

## PROMPT
You received an offer letter (see attached PDF) for a new employee. Complete the onboarding: create the employee, assign the correct department, set up employment details with percentage and annual salary, and configure standard working hours.

### FILE ATTACHMENT
files/tilbudsbrev_en_05.pdf

## SCORE
0/14

## NOTES
Creating dummy data to be able to create employee. This is wrong, it should assign the correct department! The validation steps I added before seems to always be wrong (this is probably the case for almost all validations we have now). There is always a better solution we must find instead of running hallucinated validation. We have to read the PDF!

---

# SUBMISSION 3

## PROMPT
Le paiement de Colline SARL (nº org. 916057903) pour la facture "Maintenance" (8300 NOK HT) a été retourné par la banque. Annulez le paiement afin que la facture affiche à nouveau le montant impayé.

## SCORE
4/8

## NOTES
No visible API errors. Must investigate logs.

---

# SUBMISSION 4

## PROMPT
Precisamos da despesa de Overnatting deste recibo registada no departamento Utvikling. Use a conta de despesas correta e garanta o tratamento correto do IVA.

### FILE ATTACHMENT
files/kvittering_pt_08.pdf

## SCORE
0/10

## NOTES
No API errors. But something is going wrong. Look at the logs. Can it be the validation steps and that we do not read and use the PDF data well enough?

---

# SUBMISSION 5

## PROMPT
Set a fixed price of 170500 NOK on the project "Infrastructure Upgrade" for Brightstone Ltd (org no. 850116091). The project manager is Charlotte Walker (charlotte.walker@example.org). Invoice the customer for 33% of the fixed price as a milestone payment.

## SCORE
2/8

## NOTES
Here as well, all the stupid 'ensure' logic. We need to make sure that this is removed and that we instead find better solutions by researching the API specs. After that there comes some API errors as well, look into if we need to fix anything there. 

