"use client";

import { FileUp, FlaskConical } from "lucide-react";
import { useApp } from "@/lib/store";
import { Button, ButtonLink } from "../ui/button";
import { EmptyState } from "../ui/states";

export function NoDataState() {
  const { setMode } = useApp();
  return (
    <EmptyState icon={FileUp} title="No statements imported yet"
      action={<>
        <ButtonLink href="/app/import" variant="primary"><FileUp className="h-4 w-4" aria-hidden="true" />Import a statement</ButtonLink>
        <Button onClick={() => setMode("demo")}><FlaskConical className="h-4 w-4" aria-hidden="true" />Explore demo data</Button>
      </>}>
      Spendly turns a bank or PhonePe statement PDF into categorized transactions, then shows where your money went,
      what changed and what repeats. Your PDF is read in memory and never stored. The demo uses synthetic data, not yours.
    </EmptyState>
  );
}

