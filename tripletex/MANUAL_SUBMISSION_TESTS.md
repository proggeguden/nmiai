# SUBMISSION 1

## PROMPT

Crie o produto "Leite fresco" com número de produto 7872. O preço é 46250 NOK sem IVA, utilizando a taxa de IVA para alimentos de 15 %.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

Create the product 'Fresh Milk' with product number 7872. The price is 46,250 NOK excluding VAT, applying the 15% VAT rate for food products.

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

7/7

## CURRENT STATUS OF AGENT SOLUTION

Everything seems to be working. Hard to tell if the data created is correct, I am not able to map to true score.

—



# SUBMISSION 2

## PROMPT

Les coûts totaux ont augmenté de manière significative de janvier à février 2026. Analysez le grand livre et identifiez les trois comptes de charges avec la plus forte augmentation. Créez un projet interne pour chacun des trois comptes avec le nom du compte. Créez également une activité pour chaque projet.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

Total costs have increased significantly from January to February 2026. Analyze the general ledger and identify the three expense accounts with the largest increase. Create an internal project for each of the three accounts, using the account name. Also create an activity for each project.

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

0/10

## CURRENT STATUS OF AGENT SOLUTION

Step 3 is an analyze_response step, which is super slow and hits timeout. "Executing step 3: Identify the 3 expense accounts with the highest cost increase”. This was probably not the case before, and it does not work now. 


—



# SUBMISSION 3

## PROMPT

Sett fastpris 478900 kr på prosjektet "Automatiseringsprosjekt" for Strandvik AS (org.nr 858540402). Prosjektleiar er Bjørn Aasen (bjrn.aasen@example.org). Fakturer kunden for 25 % av fastprisen som ei delbetaling.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

Set a fixed price of NOK 478,900 for the project 'Automation Project' for Strandvik AS (org. no. 858540402). The project manager is Bjørn Aasen (bjrn.aasen@example.org). Invoice the customer for 25% of the fixed price as a partial payment.

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

6/8

## CURRENT STATUS OF AGENT SOLUTION

No API errors. Hard to tell what is wrong.



—



# SUBMISSION 4

## PROMPT

We sent an invoice for 1791 EUR to Silveroak Ltd (org no. 906661551) when the exchange rate was 11.03 NOK/EUR. The customer has now paid, but the rate is 10.66 NOK/EUR. Register the payment and post the exchange rate difference (disagio) to the correct account.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

N/A

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

7/10

## CURRENT STATUS OF AGENT SOLUTION

No API errors. Hard to tell what is wrong. Maybe the math? Should we solve math better? Or can tripletex handle this automatically somehow?



—



# SUBMISSION 5

## PROMPT

You received an offer letter (see attached PDF) for a new employee. Complete the onboarding: create the employee, assign the correct department, set up employment details with percentage and annual salary, and configure standard working hours.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

N/A

### FILE ATTACHMENT

files/tilbudsbrev_en_01.pdf

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

0 - TIMEOUT

## CURRENT STATUS OF AGENT SOLUTION

Fails, and then says ‘HEALED via replan’. But then it fails again. It looks like the solution is really really bad.


—



# SUBMISSION 6

## PROMPT

Exécutez le cycle de vie complet du projet 'Migration Cloud Montagne' (Montagne SARL, nº org. 815119924) : 1) Le projet a un budget de 489850 NOK. 2) Enregistrez le temps : Louis Moreau (chef de projet, louis.moreau@example.org) 33 heures et Louis Dubois (consultant, louis.dubois@example.org) 108 heures. 3) Enregistrez un coût fournisseur de 48850 NOK de Soleil SARL (nº org. 981965965). 4) Créez une facture client pour le projet.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

Execute the full project lifecycle for 'Cloud Migration Montagne' (Montagne SARL, org. no. 815119924): 1) The project has a budget of NOK 489,850. 2) Record time entries: Louis Moreau (project manager, louis.moreau@example.org) 33 hours and Louis Dubois (consultant, louis.dubois@example.org) 108 hours. 3) Record a supplier cost of NOK 48,850 from Soleil SARL (org. no. 981965965). 4) Generate a customer invoice for the project.

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

6/11

## CURRENT STATUS OF AGENT SOLUTION

A lot of things happening. 404 error. Must be checked. 


—



# SUBMISSION 7

## PROMPT

Reconcile the bank statement (attached CSV) against open invoices in Tripletex. Match incoming payments to customer invoices and outgoing payments to supplier invoices. Handle partial payments correctly.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

N/A

### FILE ATTACHMENT

files/bankutskrift_en_08.csv

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

0 - TIMEOUT

## CURRENT STATUS OF AGENT SOLUTION

The planner is invoked. But nothing more happens… 504 status code. After submitting submission 8, the planner returned 19 steps, but post deadline, so it aborted them.

—



# SUBMISSION 8

## PROMPT

Voce recebeu um contrato de trabalho (ver PDF anexo). Crie o funcionario no Tripletex com todos os detalhes do contrato: numero de identidade nacional, data de nascimento, departamento, codigo de ocupacao, salario, percentagem de emprego e data de inicio.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

You have received an employment contract (see attached PDF). Create the employee in Tripletex with all details from the contract: national identity number, date of birth, department, occupation code, salary, employment percentage, and start date.

### FILE ATTACHMENT

files/arbeidskontrakt_pt_03.pdf

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

0 - TIMEOUT

## CURRENT STATUS OF AGENT SOLUTION

Proposed solution does not look good. Creates dummy department and company division (says it is required for employment). Then references errors are coming, and it times out. Maybe there are more information in the PDF than what is stated in the prompt, so we can find the correct department etc. The tripletex API docs should be checked to see what can be done as well.

—


# SUBMISSION 9

## PROMPT

Enviamos una factura por 9487 EUR a Estrella SL (org. nº 834293692) cuando el tipo de cambio era 11.54 NOK/EUR. El cliente ha pagado ahora, pero el tipo es 10.95 NOK/EUR. Registre el pago y contabilice la diferencia de tipo de cambio (disagio) en la cuenta correcta.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

We issued an invoice of EUR 9,487 to Estrella SL (org. no. 834293692) when the exchange rate was 11.54 NOK/EUR. The customer has now paid, but the rate is 10.95 NOK/EUR. Record the payment and recognize the exchange rate loss (disagio) in the appropriate account.

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

7/10

## CURRENT STATUS OF AGENT SOLUTION

No API errors, so hard to tell what is wrong. Must check logs.

—



# SUBMISSION 10

## PROMPT

Du har motteke ein leverandorfaktura (sjaa vedlagt PDF). Registrer fakturaen i Tripletex. Opprett leverandoren viss den ikkje finst. Bruk rett utgiftskonto og inngaaande MVA.

### PROMPT TRANSLATED TO ACCOUNTING ENGLISH BY AI

You have received a supplier invoice (see attached PDF). Record the invoice in Tripletex. Create the supplier if it does not already exist. Use the appropriate expense account and input VAT.

### FILE ATTACHMENT

files/leverandorfaktura_nn_04.pdf

## CHECK SCORE (FROM SUBMISSION PAGE, NOT VISIBLE FOR AI AGENT)

0/10

## CURRENT STATUS OF AGENT SOLUTION

422 API errors, and then a some ‘unresolved refs’ errors. Hopefully the unresolved refs errors appear because of the 422 errors. Look at the logs.


—

