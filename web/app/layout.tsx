import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { MotionProvider } from "@/components/motion-provider";
import { site } from "@/lib/site";
import "./globals.css";

const title = "Spendly — Personal finance intelligence for your bank statements";

export const metadata: Metadata = {
  metadataBase: new URL(site.siteUrl),
  title: { default: title, template: "%s · Spendly" },
  description: site.description,
  applicationName: "Spendly",
  keywords: ["personal finance", "UPI", "bank statement analyzer", "spending insights", "India", "SQL analytics"],
  openGraph: {
    type: "website",
    title,
    description: site.description,
    siteName: "Spendly",
    locale: "en_IN",
  },
  twitter: { card: "summary_large_image", title, description: site.description },
};

export const viewport: Viewport = {
  themeColor: "#080a08",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className={`${GeistSans.variable} ${GeistMono.variable} antialiased`}>
      <body className="grain min-h-dvh bg-ink text-fg">
        <a
          href="#main"
          className="sr-only z-[70] rounded-lg bg-lime px-4 py-2 font-medium text-ink focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
        >
          Skip to content
        </a>
        <MotionProvider>{children}</MotionProvider>
      </body>
    </html>
  );
}
