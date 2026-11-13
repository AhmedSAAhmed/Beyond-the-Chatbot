# Intent taxonomy

Closed set. The first 27 are the Bitext customer-support intents (so accuracy can be measured against Bitext labels); the last 11 cover what real public traffic contains that Bitext does not. `app/taxonomy.py` parses this table, so keep the format.

| intent | group | meaning |
|---|---|---|
| cancel_order | ORDER | wants to cancel an order |
| change_order | ORDER | wants to change items or quantity in an order |
| place_order | ORDER | wants help buying something |
| track_order | ORDER | asks where an order is |
| change_shipping_address | SHIPPING | wants to change a delivery address |
| set_up_shipping_address | SHIPPING | wants to add a delivery address |
| check_cancellation_fee | CANCEL | asks about a cancellation fee |
| check_invoice | INVOICE | wants to see an invoice |
| get_invoice | INVOICE | wants an invoice sent |
| check_payment_methods | PAYMENT | asks which payment methods exist |
| payment_issue | PAYMENT | a payment failed, was declined, or charged wrongly / twice |
| check_refund_policy | REFUND | asks about refund rules |
| get_refund | REFUND | wants money back |
| track_refund | REFUND | asks where a refund is |
| complaint | FEEDBACK | general complaint about service, no more specific intent fits |
| review | FEEDBACK | wants to leave or discuss a product review |
| contact_customer_service | CONTACT | wants to reach support |
| contact_human_agent | CONTACT | wants a human, not a bot |
| create_account | ACCOUNT | wants an account |
| delete_account | ACCOUNT | wants an account closed |
| edit_account | ACCOUNT | wants to change account details |
| recover_password | ACCOUNT | locked out / forgot password |
| registration_problems | ACCOUNT | sign-up fails |
| switch_account | ACCOUNT | wants to switch account / plan |
| delivery_options | DELIVERY | asks which delivery options exist |
| delivery_period | DELIVERY | asks how long delivery takes |
| newsletter_subscription | SUBSCRIPTION | newsletter on/off |
| delivery_problem | DELIVERY | delivery late, missed, mishandled, left unsafe, promised date broken |
| damaged_or_defective | PRODUCT | item arrived broken, faulty, or stopped working |
| wrong_or_misdescribed_item | PRODUCT | wrong item, wrong size/colour, not as described |
| price_or_promo_issue | PAYMENT | price dropped after purchase, deal or promo code not applied |
| website_or_app_bug | TECH | site or app broken, button not working, errors |
| packaging_feedback | FEEDBACK | complaint or comment about packaging |
| membership_issue | SUBSCRIPTION | Prime / membership benefits, fees, renewals |
| digital_content | TECH | streaming, e-books, devices, ads on devices |
| account_security | ACCOUNT | hacked account, fraud, phishing |
| praise | FEEDBACK | thanks or compliments |
| other | OTHER | none of the above, or not a customer-service message |
