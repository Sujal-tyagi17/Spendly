import { BeforeAfter } from "@/components/before-after";
import { Features } from "@/components/features";
import { FinalCta } from "@/components/final-cta";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { HowItWorks } from "@/components/how-it-works";
import { Nav } from "@/components/nav";
import { Privacy } from "@/components/privacy";
import { ProductPreview } from "@/components/product-preview";
import { SqlSection } from "@/components/sql-section";

export default function Home() {
  return (
    <>
      <Nav />
      <main id="main">
        <Hero />
        <ProductPreview />
        <BeforeAfter />
        <Features />
        <HowItWorks />
        <SqlSection />
        <Privacy />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}
