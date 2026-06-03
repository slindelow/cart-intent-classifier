/**
 * Cart Abandonment Intent Classifier — Shopify Pixel
 *
 * Captures session behaviour signals and sends them to the FastAPI backend.
 * Deploy via Shopify Admin → Settings → Customer Events → Add custom pixel.
 *
 * Replace BACKEND_URL with your Railway deployment URL.
 */

const BACKEND_URL = "https://your-railway-url.up.railway.app";

// ── Session ID ────────────────────────────────────────────────────────────────
// Use the Shopify checkout token as session ID so pixel events and the
// cart-abandoned webhook can be correlated server-side.

let sessionId = null;
let customerId = null;
let checkoutStartTime = null;

// ── Helpers ───────────────────────────────────────────────────────────────────

function sendEvent(event, extra = {}) {
  const payload = {
    session_id: sessionId,
    customer_id: customerId,
    event,
    timestamp: Math.floor(Date.now() / 1000),
    ...extra,
  };

  // Use sendBeacon for reliability on page unload events
  if (navigator.sendBeacon) {
    const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
    navigator.sendBeacon(`${BACKEND_URL}/webhook/session-event`, blob);
  } else {
    fetch(`${BACKEND_URL}/webhook/session-event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {}); // Swallow errors — pixel should never break storefront
  }
}

// ── Event subscriptions ───────────────────────────────────────────────────────

// Every page view — captures policy page visits
analytics.subscribe("page_viewed", (event) => {
  const url = event.context?.document?.location?.href || "";

  // Set session ID from checkout token if available
  if (!sessionId && event.context?.checkout?.token) {
    sessionId = event.context.checkout.token;
  }

  // Set customer ID if the customer is logged in
  if (!customerId && event.context?.customer?.id) {
    customerId = String(event.context.customer.id);
  }

  sendEvent("page_viewed", { url });
});

// Checkout started — begin timing
analytics.subscribe("checkout_started", (event) => {
  sessionId = sessionId || event.checkout?.token;
  checkoutStartTime = Math.floor(Date.now() / 1000);
  sendEvent("checkout_started", {
    cart_value: event.checkout?.totalPrice?.amount,
    item_count: event.checkout?.lineItems?.length || 0,
  });
});

// Cart updated — track items removed (sign of indecision)
analytics.subscribe("cart_updated", (event) => {
  const previousCount = event.previousCart?.lines?.length || 0;
  const currentCount = event.cart?.lines?.length || 0;

  if (currentCount < previousCount) {
    sendEvent("cart_updated", { action: "removed" });
  } else if (currentCount > previousCount) {
    sendEvent("cart_updated", { action: "added" });
  }
});

// Product viewed — signals research behaviour
analytics.subscribe("product_viewed", (event) => {
  sendEvent("product_viewed", {
    product_id: event.productVariant?.product?.id,
    product_title: event.productVariant?.product?.title,
  });
});

// Checkout completed — clean signal that this customer converted
// (used server-side to avoid classifying converted customers)
analytics.subscribe("checkout_completed", (event) => {
  sendEvent("checkout_completed");
});
