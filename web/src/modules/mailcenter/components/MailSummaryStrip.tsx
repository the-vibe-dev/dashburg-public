import { Card, CardContent } from "../../../shared/components/ui/card";

type SummaryCard = {
  label: string;
  value: string;
  key: string;
};

export function MailSummaryStrip({ cards }: { cards: SummaryCard[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {cards.map((card) => (
        <Card key={card.key} className="bg-card/80 backdrop-blur">
          <CardContent className="py-4">
            <p className="text-xs text-muted-foreground">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight">{card.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
