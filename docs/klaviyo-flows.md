# Klaviyo Flow Specs — Cart Abandonment Intent Classifier

Four flows, each triggered by the `abandoned_cart_intent` profile property written by the classifier.

**Trigger type (all flows):** Profile Property Updated
**Property:** `abandoned_cart_intent`
**Value:** (specific to each flow, see below)

---

## How to set up the trigger in Klaviyo

1. Flows → Create Flow → Create from Scratch
2. Trigger: **"Metric"** → select **"Profile Property Updated"** (or use **"Klaviyo Event"** if writing via API)
3. Add a trigger filter: `abandoned_cart_intent` **equals** `[value]`
4. Add a flow filter: `Placed Order` **zero times since** `starting this flow` (suppress converters)

---

## Flow 1 — Abandoned Cart: Discount Offer

**Trigger filter:** `abandoned_cart_intent` equals `price_sensitive`

**Who gets this:** High discount usage rate, cart value significantly above their AOV, or comparison shopping signals.

**Strategy:** Lead with the offer. Don't make them hunt for it. Two-email sequence — the discount, then a last-chance nudge before it expires.

### Architecture

```
[Trigger: abandoned_cart_intent = price_sensitive]
        ↓
  Wait 1 hour
        ↓
  Email 1: The Offer
        ↓
  Time Delay: 20 hours
        ↓
  Conditional Split: Placed Order since flow started?
    YES → Exit (no more emails)
    NO  → Email 2: Last Chance
        ↓
  Exit
```

### Email 1 — The Offer

**Subject:** Here's 15% off — it's yours until tomorrow
**Preview text:** Your cart is waiting. Use SAVE15 at checkout.

---

**Body:**

Hey [First Name],

You left something in your cart. We noticed — and we want to make it easier to say yes.

**Use code SAVE15 for 15% off your order.**

This code expires in 24 hours.

[Your cart items — dynamic block]

**[Complete My Order →]**

Questions? Hit reply — we're real people.

— [Brand Name]

*Offer valid for 24 hours from when this email was sent. Cannot be combined with other offers.*

---

### Email 2 — Last Chance

**Subject:** Your 15% off expires tonight
**Preview text:** SAVE15 — last few hours.

---

**Body:**

Hey [First Name],

Quick heads up: your 15% off code expires tonight at midnight.

**SAVE15** — use it before it's gone.

[Your cart items — dynamic block]

**[Claim My Discount →]**

— [Brand Name]

---

---

## Flow 2 — Abandoned Cart: Confidence Builder

**Trigger filter:** `abandoned_cart_intent` equals `trust_gap`

**Who gets this:** First-time buyers with a high-value cart, or anyone who visited the returns or shipping policy page before dropping off.

**Strategy:** Don't lead with the product. Lead with reassurance. They want to buy — they just need to feel safe doing it.

### Architecture

```
[Trigger: abandoned_cart_intent = trust_gap]
        ↓
  Wait 1 hour
        ↓
  Email 1: Trust Signals
        ↓
  Wait 48 hours
        ↓
  Conditional Split: Placed Order since flow started?
    YES → Exit
    NO  → Email 2: Social Proof
        ↓
  Exit
```

### Email 1 — Trust Signals

**Subject:** A few things worth knowing before you decide
**Preview text:** Free returns. Real reviews. No risk.

---

**Body:**

Hey [First Name],

Still thinking it over? That's fair — it's a considered purchase.

Here's what we want you to know:

**Free returns, no questions asked.**
If it's not right, send it back within 30 days. On us.

**[X] five-star reviews.**
[Pull in review snippet — e.g. "I was hesitant too. Now it's my favourite purchase this year." — @customer_handle]

**Secure checkout.**
Your payment info is encrypted and never stored.

Your cart is saved whenever you're ready.

[Your cart items — dynamic block]

**[Complete My Order →]**

— [Brand Name]

---

### Email 2 — Social Proof

**Subject:** Someone who felt the same way
**Preview text:** They were on the fence too.

---

**Body:**

Hey [First Name],

We hear from a lot of customers who weren't sure at first.

Here's what they said after:

*"I almost didn't buy it. Now I recommend it to everyone I know."*
— [Customer Name], [City]

*"The returns process was so easy — but I didn't need it."*
— [Customer Name], [City]

[Your cart is still saved]

**[I'm Ready →]**

Still have questions? Reply to this email — we'll get back to you within a few hours.

— [Brand Name]

---

---

## Flow 3 — Abandoned Cart: Simple Reminder

**Trigger filter:** `abandoned_cart_intent` equals `distracted`

**Who gets this:** Returning customers with a normal-sized cart, short session, no policy page visits. They meant to buy — something just got in the way.

**Strategy:** One email. Clean and minimal. No discount (they don't need it), no pressure. Just a clear path back.

### Architecture

```
[Trigger: abandoned_cart_intent = distracted]
        ↓
  Wait 2 hours
        ↓
  Email 1: The Reminder
        ↓
  Exit
```

### Email 1 — The Reminder

**Subject:** You left something behind
**Preview text:** Your cart is still here.

---

**Body:**

Hey [First Name],

Looks like you got pulled away. Your cart is still waiting.

[Your cart items — dynamic block]

**[Pick Up Where I Left Off →]**

— [Brand Name]

---

*One email. That's it. No follow-up.*

---

---

## Flow 4 — Abandoned Cart: Education

**Trigger filter:** `abandoned_cart_intent` equals `research_phase`

**Who gets this:** Customers who added and removed items, viewed multiple products, have low email engagement. Still in evaluation mode — not ready to buy, not scared off. Just thinking.

**Strategy:** Don't push. Give them what they need to make the decision themselves. Three emails over five days — content-first, cart-second.

### Architecture

```
[Trigger: abandoned_cart_intent = research_phase]
        ↓
  Wait 4 hours
        ↓
  Email 1: The Benefits
        ↓
  Wait 2 days
        ↓
  Conditional Split: Placed Order since flow started?
    YES → Exit
    NO  → Email 2: The FAQ
        ↓
  Wait 3 days
        ↓
  Conditional Split: Placed Order since flow started?
    YES → Exit
    NO  → Email 3: The Comparison
        ↓
  Exit
```

### Email 1 — The Benefits

**Subject:** Still researching? Here's what you should know.
**Preview text:** The short version of what makes this different.

---

**Body:**

Hey [First Name],

You've been looking at [Product Name]. We thought it might help to cut through the noise.

**What it actually does:**
[2-3 concrete, specific benefit bullets — not marketing copy. Real outcomes.]
- [e.g. "Works within 2 weeks — most customers notice a difference in 10-14 days"]
- [e.g. "Formulated without X, Y, Z — so it's safe for sensitive skin"]
- [e.g. "One bottle lasts ~90 days at the recommended dose"]

**Who it's for:**
[One clear sentence about ideal customer/use case]

**Who it's not for:**
[Honest line — builds trust and filters in the right customers]

[Your cart — dynamic block]

**[Learn More →]** or **[I'm Ready to Order →]**

— [Brand Name]

---

### Email 2 — The FAQ

**Subject:** The questions we get asked most
**Preview text:** Answered honestly.

---

**Body:**

Hey [First Name],

A few questions we get a lot — figured they might be on your mind too.

**"How long until I see results?"**
[Honest answer]

**"What if it doesn't work for me?"**
[Returns policy / guarantee — reinforce it]

**"Is it worth the price compared to [cheaper alternative]?"**
[Direct, confident answer — don't dodge this one]

**"Can I use it with [X]?"**
[Compatibility note if relevant]

Still have a question we didn't answer? Reply — we read every email.

[Your cart — dynamic block]

**[I'm Ready →]**

— [Brand Name]

---

### Email 3 — The Comparison

**Subject:** One last thing before you decide
**Preview text:** How we stack up — honestly.

---

**Body:**

Hey [First Name],

If you're comparing options, here's the honest version:

| | [Brand Name] | Typical alternative |
|---|---|---|
| [Key differentiator 1] | ✓ | ✗ |
| [Key differentiator 2] | ✓ | Sometimes |
| Returns | 30 days, free | Varies |
| Price per [unit/use] | $[X] | $[Y] |

We're not the cheapest option. We're not trying to be.

[What we are: one clear positioning statement]

If that's what you're looking for, we'd love to have you as a customer.

**[Complete My Order →]**

— [Brand Name]

---

---

## Klaviyo Setup Checklist

- [ ] Create free Klaviyo account at klaviyo.com
- [ ] Connect Shopify store (Klaviyo has a native Shopify integration)
- [ ] Create custom profile property: `abandoned_cart_intent` (type: string)
- [ ] Create custom profile property: `abandoned_cart_flow` (type: string)
- [ ] Build Flow 1: Discount Offer
- [ ] Build Flow 2: Confidence Builder
- [ ] Build Flow 3: Simple Reminder
- [ ] Build Flow 4: Education
- [ ] Add global flow filter to all four flows: "Placed Order zero times since starting this flow"
- [ ] Test each flow using Klaviyo's preview + test send
- [ ] Verify `abandoned_cart_intent` property update fires the correct flow (use a test profile)
