import type { Metadata } from "next";
import { AppShell } from "@/components/app/shell";
import { AppProvider } from "@/lib/store";

export const metadata: Metadata = {
  title: "App",
  description: "Spendly — explore your spending, recurring payments and data quality.",
  robots: { index: false },
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppProvider>
      <AppShell>{children}</AppShell>
    </AppProvider>
  );
}
