import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { useI18n } from "../app/i18n";
import { SectionCard } from "../components/SectionCard";
import { getLearningProductDetail } from "../lib/api";

export const LearningDetailPage = () => {
  const { t } = useI18n();
  const { kind = "", fileName = "" } = useParams();
  const detailQuery = useQuery({
    queryKey: ["learning-product-detail", kind, fileName],
    queryFn: () => getLearningProductDetail(kind, fileName),
    enabled: Boolean(kind && fileName),
  });

  const detail = detailQuery.data;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">Learning Detail</p>
          <h1>{fileName}</h1>
          <p>{kind}</p>
        </div>
      </header>

      <SectionCard title="Payload" subtitle="Stored learning artifact details.">
        {detail ? (
          <pre className="code-block">{JSON.stringify(detail.payload, null, 2)}</pre>
        ) : (
          <p className="empty-state">{t("overview.error")}</p>
        )}
      </SectionCard>
    </div>
  );
};
