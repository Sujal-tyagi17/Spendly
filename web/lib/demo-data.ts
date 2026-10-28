/**
 * ILLUSTRATIVE, SYNTHETIC DATA.
 *
 * These numbers come from Spendly's built-in synthetic demo dataset
 * (data/sample_transactions.csv in the repository, April–September 2026).
 * They describe no real person. Every preview on the site is labelled as such.
 */

export type Month = { label: string; spend: number; income: number };

/** Monthly expenditure and income, in rupees (from the demo dataset). */
export const months: Month[] = [
  { label: "Apr", spend: 39696, income: 65000 },
  { label: "May", spend: 49096, income: 65000 },
  { label: "Jun", spend: 51507, income: 65288 },
  { label: "Jul", spend: 43054, income: 65000 },
  { label: "Aug", spend: 102186, income: 65000 },
  { label: "Sep", spend: 40088, income: 65220 },
];

export const currentMonth = {
  label: "September 2026",
  spend: 40088,
  previous: 102186,
  changePct: -60.8,
};

/** September 2026 expenditure by category (rupees, share of expenditure). */
export const categories = [
  { name: "Rent & Housing", amount: 18000, share: 44.9 },
  { name: "Groceries", amount: 6985, share: 17.4 },
  { name: "Food & Dining", amount: 3370, share: 8.4 },
  { name: "Other", amount: 3140, share: 7.8 },
  { name: "Transport", amount: 2285, share: 5.7 },
  { name: "Bills & Utilities", amount: 1999, share: 5.0 },
];

export type Txn = {
  date: string;
  merchant: string;
  category: string;
  amount: number; // negative = money out
  raw: string;
};

/** Recent transactions as Spendly shows them, with the raw statement line they came from. */
export const transactions: Txn[] = [
  { date: "30 Sep", merchant: "Namma Metro", category: "Transport", amount: -240,
    raw: "UPI/DR/XXXX0219/NAMMA METRO BMRCL/YESB/[upi-id]/Payment" },
  { date: "30 Sep", merchant: "Interest", category: "Income", amount: 220,
    raw: "SB INT CREDIT/QTR ENDING" },
  { date: "26 Sep", merchant: "ATM cash withdrawal", category: "Other", amount: -2000,
    raw: "ATM WDL/XXXX9012/MG ROAD BRANCH" },
  { date: "24 Sep", merchant: "Amazon", category: "Shopping", amount: -1743,
    raw: "POS/XXXX9012/AMZN MKTPLACE" },
  { date: "23 Sep", merchant: "Uber", category: "Transport", amount: -380,
    raw: "UPI/DR/XXXX0221/UBER INDIA/YESB/[upi-id]/Payment" },
  { date: "20 Sep", merchant: "JioHotstar", category: "Subscriptions", amount: -299,
    raw: "UPI/DR/XXXX0199/JIOHOTSTAR/UTIB/[upi-id]/Payment" },
];

/** Raw lines → structured rows, for the before/after section. */
export const rawToStructured = [
  { raw: "UPI/DR/412345678901/ZOMATO*ORDER6943/YESB/zomato@ybl/Payment",
    merchant: "Zomato", category: "Food & Dining", type: "Expense", amount: -650 },
  { raw: "IMPS/DR/600000000113/SELF TRANSFER TO OWN A/C XXXXXX4521",
    merchant: "Own account transfer", category: "Transfers", type: "Excluded from spending", amount: -10000 },
  { raw: "BILLDESK/CREDIT CARD PAYMENT/HDFC CARD XXXX9012",
    merchant: "Credit card bill", category: "Transfers", type: "Not double-counted", amount: -7150 },
  { raw: "UPI/CR/600000000231/AMAZON REFUND/UTIB/amazon@apl/Payment",
    merchant: "Amazon", category: "Refunds", type: "Refund", amount: 1299 },
  { raw: "ACH/DR/600000000115/NETFLIX.COM",
    merchant: "Netflix", category: "Subscriptions", type: "Recurring · monthly", amount: -649 },
];

export const recurring = [
  { merchant: "House rent", cadence: "Monthly", amount: 18000 },
  { merchant: "Cult.fit", cadence: "Monthly", amount: 1499 },
  { merchant: "Netflix", cadence: "Monthly", amount: 649 },
  { merchant: "Airtel", cadence: "Monthly", amount: 624 },
  { merchant: "JioHotstar", cadence: "Monthly", amount: 299 },
  { merchant: "Spotify", cadence: "Monthly", amount: 119 },
];

/** Amazon payments in the demo data — one stands far above the rest. */
export const amazonPayments = [2705, 2155, 1299, 54999, 530, 1743];

export const formatINR = (value: number, opts: { sign?: boolean } = {}) => {
  const abs = Math.abs(Math.round(value)).toLocaleString("en-IN");
  const sign = value < 0 ? "−" : opts.sign && value > 0 ? "+" : "";
  return `${sign}₹${abs}`;
};

export const formatCompactINR = (value: number) => {
  const abs = Math.abs(value);
  if (abs >= 100000) return `₹${(value / 100000).toFixed(abs >= 1000000 ? 0 : 1).replace(/\.0$/, "")}L`;
  if (abs >= 1000) return `₹${(value / 1000).toFixed(0)}K`;
  return `₹${value}`;
};
