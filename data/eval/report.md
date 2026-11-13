pass

# Stage 02 intent accuracy on Bitext

- Examples: 540 across 27 intents (stratified sample, seed 7)
- Model calls by provider: {'groq:openai/gpt-oss-120b': 10, 'gemini:gemini-3.5-flash-lite': 18, 'groq:qwen/qwen3.8-27b': 1, 'gemini:gemini-2.5-flash': 2, 'gemini:gemini-3.1-flash-lite': 5}
- Accuracy: **96.1%** (519/540)
- Classifier: `app/pipeline/infer.py` with the prompt in `stages/02_infer-intent/references/prompt.md`, unchanged from production.
- The model chooses from all 38 intents (Bitext 27 + 11 real-world), so a pick from the extra 11 counts as wrong.

| intent | correct |
|---|---|
| cancel_order | 19/20 |
| change_order | 20/20 |
| change_shipping_address | 20/20 |
| check_cancellation_fee | 20/20 |
| check_invoice | 20/20 |
| check_payment_methods | 20/20 |
| check_refund_policy | 19/20 |
| complaint | 17/20 |
| contact_customer_service | 18/20 |
| contact_human_agent | 20/20 |
| create_account | 20/20 |
| delete_account | 20/20 |
| delivery_options | 20/20 |
| delivery_period | 12/20 |
| edit_account | 20/20 |
| get_invoice | 20/20 |
| get_refund | 19/20 |
| newsletter_subscription | 20/20 |
| payment_issue | 20/20 |
| place_order | 20/20 |
| recover_password | 20/20 |
| registration_problems | 20/20 |
| review | 20/20 |
| set_up_shipping_address | 20/20 |
| switch_account | 20/20 |
| track_order | 20/20 |
| track_refund | 15/20 |

Most common confusions (true -> predicted):

- delivery_period -> track_order: 8
- track_refund -> get_refund: 5
- complaint -> contact_customer_service: 3
- contact_customer_service -> contact_human_agent: 2
- cancel_order -> payment_issue: 1
- check_refund_policy -> track_refund: 1
- get_refund -> check_refund_policy: 1
