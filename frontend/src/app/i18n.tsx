import {
  createContext,
  type PropsWithChildren,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type Locale = "en" | "ko";

type TranslationTree = {
  [key: string]: string | TranslationTree;
};

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

const STORAGE_KEY = "ontro-finance-locale";

const messages: Record<Locale, TranslationTree> = {
  en: {
    layout: {
      eyebrow: "onTro Finance",
      title: "Operations Workbench",
      copy: "Internal web console for ingest review, graph inspection, council handling, and reasoning support.",
      navLabel: "Primary navigation",
      nav: {
        overview: "Overview",
        intake: "Data Intake",
        saved: "Saved Data",
        graph: "Graph Explorer",
        council: "Council & Ask",
      },
    },
    common: {
      status: {
        ready: "ready",
        loading: "loading",
        healthy: "healthy",
        degraded: "degraded",
        initializing: "initializing",
      },
      edgesExtracted: "{{count}} edges extracted",
      documentId: "Document ID",
      openSavedRecord: "Open saved record",
      openGraphExplorer: "Open graph explorer",
      openCouncil: "Open council",
      question: "Question",
      confidence: "Confidence",
      destinations: {
        domain: "Domain",
        personal: "Personal",
        council: "Council",
      },
    },
    overview: {
      eyebrow: "Control Surface",
      title: "Overview",
      description: "Monitor intake volume, relation coverage, and council pressure from one place.",
      stats: {
        ingests: "Documents ingested",
        entities: "Entities tracked",
        relations: "Relations tracked",
        councilPending: "Council pending",
      },
      recent: {
        title: "Recent Intake",
        subtitle: "The latest items ready for inspection or follow-up.",
        empty: "No recent ingest records yet.",
      },
      council: {
        title: "Council Readiness",
        subtitle: "Pending reviews, closed work, and active members.",
        pending: "Pending cases",
        closed: "Closed cases",
        available: "Available members",
      },
      trust: {
        title: "Trust Signals",
        subtitle: "Confidence distribution, validation routing, and council triggers.",
        confidence: "Confidence bands",
        destinations: "Validation routes",
        triggers: "Top triggers",
        empty: "No trust signals are available yet.",
      },
      learning: {
        title: "Learning Products",
        subtitle: "Current dataset, evaluation, goldset, and bundle inventory.",
        snapshots: "Snapshots",
        evaluations: "Evaluations",
        bundles: "Bundles",
        goldsets: "Goldsets",
      },
      audit: {
        title: "Audit Trail",
        subtitle: "Recent operator and API actions recorded by the service.",
        empty: "No audit events recorded yet.",
      },
      error: "Dashboard data could not be loaded.",
    },
    intake: {
      eyebrow: "Pipeline Input",
      title: "Data Intake",
      description: "Submit raw text or a PDF, then move directly into the saved record and council follow-up.",
      text: {
        title: "Text Intake",
        subtitle: "Paste analysis, notes, or market commentary.",
        label: "Analysis text",
        submit: "Submit text",
        error: "Text ingest failed.",
      },
      pdf: {
        title: "PDF Intake",
        subtitle: "Upload a report or internal brief for extraction.",
        label: "PDF file",
        submit: "Submit PDF",
        error: "PDF ingest failed.",
      },
      result: {
        title: "Latest Result",
        subtitle: "Immediate ingest feedback for the operator.",
        empty: "No ingest has been submitted in this session yet.",
      },
    },
    saved: {
      eyebrow: "Stored Records",
      title: "Saved Data",
      description: "Inspect ingest history, open a specific record, and move out to graph or council review.",
      recent: {
        title: "Recent Records",
        subtitle: "Recent source documents with linked ingest activity and evidence.",
        empty: "No saved ingest records available.",
      },
      detail: {
        title: "Record Detail",
        subtitle: "Document metadata, linked relations, and evidence traces for the selected record.",
        empty: "Select a document to view ingest detail.",
      },
      document: {
        sourceType: "Source type",
        institution: "Institution",
        author: "Author",
        filters: {
          search: "Search documents",
          sourceType: "Source type filter",
          allSources: "All sources",
        },
        relations: {
          title: "Linked Relations",
          subtitle: "{{count}} relation summary tied to this document.",
          evidenceCount: "{{count}} evidence item",
          empty: "No relation summary is available for this document yet.",
        },
        evidence: {
          title: "Evidence Trail",
          subtitle: "Validation {{validation}}, council {{council}}.",
          validation: "validation",
          unknown: "Unknown relation",
          noExcerpt: "No excerpt available.",
          empty: "No evidence events were captured for this document yet.",
        },
      },
    },
    graph: {
      eyebrow: "Graph Inspection",
      title: "Graph Explorer",
      description: "Search an entity, load a local subgraph, and review the relation story in one workspace.",
      search: {
        title: "Search",
        subtitle: "Start from a named entity or indicator.",
        label: "Entity search",
        button: "Find entity",
      },
      depth: {
        one: "Depth 1",
        two: "Depth 2",
        three: "Depth 3",
      },
      subgraph: {
        title: "Subgraph",
        subtitle: "{{count}} relation in view",
      },
      detail: {
        title: "Entity Detail",
        subtitle: "Focused context for the selected node.",
        empty: "Search and select an entity to inspect its graph footprint.",
        noRelations: "No adjacent relations are loaded yet.",
      },
    },
    council: {
      eyebrow: "Council Operations",
      title: "Council & Ask",
      description: "Review pending graph disputes, trigger retry automation, and run a reasoning query in one surface.",
      queue: {
        title: "Council Queue",
        subtitle: "Cases waiting for operator attention or worker processing.",
        process: "Process pending",
        retry: "Retry selected case",
        processedRetry: "Processed {{count}} pending case after retry.",
        processedQueue: "Processed {{count}} pending case in the queue.",
        retryError: "Retry failed. Please try again.",
        processError: "Processing failed. Please try again.",
      },
      ask: {
        title: "Ask the Graph",
        subtitle: "Run a direct reasoning query against the current knowledge graph.",
        submit: "Ask graph",
        error: "Ask graph failed. Please try again.",
      },
    },
    settings: {
      eyebrow: "Preferences",
      title: "Settings",
      openButton: "Settings",
      close: "Close",
      ai: {
        title: "AI Runtime",
        subtitle: "Inspect the active model, auth policy, and live connection state before running council or reasoning work.",
        loading: "Loading AI runtime status...",
        loadError: "AI runtime status could not be loaded.",
        check: "Check connection",
        checking: "Checking...",
        missingEnv: "Missing credentials: {{vars}}",
        fields: {
          provider: "Provider",
          auth: "Auth",
          endpoint: "Endpoint",
          attempts: "Connection attempts",
          authConfigured: "Auth configured",
          lastChecked: "Last checked",
          checkedUrl: "Checked URL",
        },
        authType: {
          none: "No auth",
          api_key: "API key",
          oauth_app: "OAuth app",
        },
        connection: {
          connected: "Connected",
          disconnected: "Disconnected",
        },
        boolean: {
          yes: "Configured",
          no: "Missing",
          notRequired: "Not required",
        },
      },
      language: {
        title: "Language",
        subtitle: "Choose the interface language used across the web console.",
        label: "Language selector",
        en: "English",
        ko: "한국어",
      },
      data: {
        title: "Selective Delete",
        subtitle: "Choose saved ingest records to remove, then rebuild the current dataset without them.",
        loading: "Loading ingest records...",
        loadError: "Saved ingest records could not be loaded.",
        empty: "No ingest records are available.",
        selectionCount: "{{count}} selected",
        selectRecord: "Select record {{docId}}",
        delete: "Delete selected",
        deletePending: "Deleting...",
        deleteSuccess: "Deleted {{count}} selected record and rebuilt the dataset.",
        deleteError: "Selected records could not be deleted.",
      },
    },
  },
  ko: {
    layout: {
      eyebrow: "온트로 파이낸스",
      title: "운영 워크벤치",
      copy: "수집 검토, 그래프 탐색, council 처리, 추론 지원을 위한 내부 웹 콘솔입니다.",
      navLabel: "기본 탐색",
      nav: {
        overview: "개요",
        intake: "데이터 수집",
        saved: "저장 데이터",
        graph: "그래프 탐색",
        council: "Council 및 질의",
      },
    },
    common: {
      status: {
        ready: "준비됨",
        loading: "불러오는 중",
        healthy: "정상",
        degraded: "성능 저하",
        initializing: "초기화 중",
      },
      edgesExtracted: "관계 {{count}}개 추출",
      documentId: "문서 ID",
      openSavedRecord: "저장 기록 열기",
      openGraphExplorer: "그래프 탐색 열기",
      openCouncil: "Council 열기",
      question: "질문",
      confidence: "신뢰도",
      destinations: {
        domain: "도메인",
        personal: "개인",
        council: "Council",
      },
    },
    overview: {
      eyebrow: "운영 현황",
      title: "개요",
      description: "수집량, 관계 범위, council 대기 상태를 한 화면에서 확인합니다.",
      stats: {
        ingests: "적재 문서 수",
        entities: "추적 엔티티 수",
        relations: "관계 수",
        councilPending: "Council 대기 건수",
      },
      recent: {
        title: "최근 수집",
        subtitle: "검토 또는 후속 조치가 필요한 최신 항목입니다.",
        empty: "최근 수집 기록이 없습니다.",
      },
      council: {
        title: "Council 상태",
        subtitle: "대기 중인 검토, 종료된 작업, 사용 가능한 멤버를 보여줍니다.",
        pending: "대기 케이스",
        closed: "종료 케이스",
        available: "사용 가능 멤버",
      },
      trust: {
        title: "신뢰 신호",
        subtitle: "신뢰도 분포, validation 라우팅, council 트리거를 보여줍니다.",
        confidence: "신뢰도 구간",
        destinations: "Validation 경로",
        triggers: "주요 트리거",
        empty: "아직 집계된 신뢰 신호가 없습니다.",
      },
      learning: {
        title: "학습 산출물",
        subtitle: "현재 dataset, evaluation, goldset, bundle 인벤토리입니다.",
        snapshots: "스냅샷",
        evaluations: "평가",
        bundles: "번들",
        goldsets: "골드셋",
      },
      audit: {
        title: "감사 로그",
        subtitle: "최근 운영자/API 액션 기록입니다.",
        empty: "기록된 감사 이벤트가 아직 없습니다.",
      },
      error: "대시보드 데이터를 불러오지 못했습니다.",
    },
    intake: {
      eyebrow: "파이프라인 입력",
      title: "데이터 수집",
      description: "텍스트나 PDF를 넣고 바로 저장 기록과 council 후속 단계로 이동합니다.",
      text: {
        title: "텍스트 수집",
        subtitle: "분석 메모, 노트, 시장 코멘터리를 붙여 넣습니다.",
        label: "분석 텍스트",
        submit: "텍스트 제출",
        error: "텍스트 수집에 실패했습니다.",
      },
      pdf: {
        title: "PDF 수집",
        subtitle: "보고서나 내부 브리프를 업로드해 추출합니다.",
        label: "PDF 파일",
        submit: "PDF 제출",
        error: "PDF 수집에 실패했습니다.",
      },
      result: {
        title: "최근 결과",
        subtitle: "운영자가 즉시 확인할 수 있는 수집 피드백입니다.",
        empty: "이번 세션에서 제출한 수집 결과가 없습니다.",
      },
    },
    saved: {
      eyebrow: "저장 기록",
      title: "저장 데이터",
      description: "수집 이력을 확인하고 특정 문서를 열어 그래프나 council 검토로 이동합니다.",
      recent: {
        title: "최근 기록",
        subtitle: "문서 메타데이터와 연결된 최신 수집/근거 기록입니다.",
        empty: "저장된 수집 기록이 없습니다.",
      },
      detail: {
        title: "기록 상세",
        subtitle: "선택한 문서의 메타데이터, 관계 요약, 근거 추적을 함께 보여줍니다.",
        empty: "문서를 선택하면 상세 정보를 볼 수 있습니다.",
      },
      document: {
        sourceType: "출처 유형",
        institution: "기관",
        author: "작성자",
        filters: {
          search: "문서 검색",
          sourceType: "출처 유형 필터",
          allSources: "전체 출처",
        },
        relations: {
          title: "연결된 관계",
          subtitle: "이 문서에 연결된 관계 요약 {{count}}건입니다.",
          evidenceCount: "근거 {{count}}건",
          empty: "이 문서에 대한 관계 요약이 아직 없습니다.",
        },
        evidence: {
          title: "근거 추적",
          subtitle: "validation {{validation}}건, council {{council}}건입니다.",
          validation: "검증",
          unknown: "알 수 없는 관계",
          noExcerpt: "본문 발췌가 없습니다.",
          empty: "이 문서에 기록된 근거 이벤트가 아직 없습니다.",
        },
      },
    },
    graph: {
      eyebrow: "그래프 점검",
      title: "그래프 탐색",
      description: "엔티티를 검색하고 로컬 서브그래프를 불러와 관계 흐름을 한 공간에서 검토합니다.",
      search: {
        title: "검색",
        subtitle: "이름이 있는 엔티티나 지표에서 시작합니다.",
        label: "엔티티 검색",
        button: "엔티티 찾기",
      },
      depth: {
        one: "깊이 1",
        two: "깊이 2",
        three: "깊이 3",
      },
      subgraph: {
        title: "서브그래프",
        subtitle: "현재 관계 {{count}}개 표시",
      },
      detail: {
        title: "엔티티 상세",
        subtitle: "선택한 노드 중심의 맥락입니다.",
        empty: "엔티티를 검색하고 선택하면 그래프 범위를 확인할 수 있습니다.",
        noRelations: "인접 관계가 아직 로드되지 않았습니다.",
      },
    },
    council: {
      eyebrow: "Council 운영",
      title: "Council 및 질의",
      description: "대기 중인 그래프 이의를 검토하고 재처리를 실행하며 추론 질의를 같은 화면에서 수행합니다.",
      queue: {
        title: "Council 대기열",
        subtitle: "운영자 확인 또는 워커 처리가 필요한 케이스입니다.",
        process: "대기 건 처리",
        retry: "선택 케이스 재시도",
        processedRetry: "재시도 후 대기 케이스 {{count}}건을 처리했습니다.",
        processedQueue: "대기열에서 케이스 {{count}}건을 처리했습니다.",
        retryError: "재시도에 실패했습니다. 다시 시도하세요.",
        processError: "처리에 실패했습니다. 다시 시도하세요.",
      },
      ask: {
        title: "그래프 질의",
        subtitle: "현재 지식 그래프를 대상으로 직접 추론 질의를 실행합니다.",
        submit: "그래프에 질문",
        error: "그래프 질의에 실패했습니다. 다시 시도하세요.",
      },
    },
    settings: {
      eyebrow: "환경 설정",
      title: "설정",
      openButton: "설정",
      close: "닫기",
      ai: {
        title: "AI 런타임",
        subtitle: "현재 사용 모델, 인증 방식, 실시간 연결 상태를 확인한 뒤 council 및 추론 작업을 진행합니다.",
        loading: "AI 런타임 상태를 불러오는 중입니다...",
        loadError: "AI 런타임 상태를 불러오지 못했습니다.",
        check: "연결 확인",
        checking: "확인 중...",
        missingEnv: "누락된 인증 정보: {{vars}}",
        fields: {
          provider: "제공자",
          auth: "인증",
          endpoint: "엔드포인트",
          attempts: "연결 시도 횟수",
          authConfigured: "인증 준비 상태",
          lastChecked: "마지막 확인 시각",
          checkedUrl: "확인 URL",
        },
        authType: {
          none: "인증 없음",
          api_key: "API 키",
          oauth_app: "OAuth 앱",
        },
        connection: {
          connected: "연결됨",
          disconnected: "연결 안 됨",
        },
        boolean: {
          yes: "준비됨",
          no: "누락됨",
          notRequired: "불필요",
        },
      },
      language: {
        title: "사용 언어",
        subtitle: "웹 콘솔 전체에 사용할 인터페이스 언어를 선택합니다.",
        label: "언어 선택",
        en: "English",
        ko: "한국어",
      },
      data: {
        title: "선택 삭제",
        subtitle: "잘못 적재한 기록을 선택해서 제거하고, 남은 데이터만 다시 구성합니다.",
        loading: "수집 기록을 불러오는 중입니다...",
        loadError: "저장된 수집 기록을 불러오지 못했습니다.",
        empty: "선택할 수집 기록이 없습니다.",
        selectionCount: "{{count}}개 선택",
        selectRecord: "{{docId}} 기록 선택",
        delete: "선택 삭제",
        deletePending: "삭제 중...",
        deleteSuccess: "선택한 기록 {{count}}개를 삭제하고 데이터를 다시 구성했습니다.",
        deleteError: "선택한 기록을 삭제하지 못했습니다.",
      },
    },
  },
};

const I18nContext = createContext<I18nContextValue | null>(null);

const resolveMessage = (tree: TranslationTree, key: string): string | null => {
  const value = key.split(".").reduce<string | TranslationTree | undefined>((current, part) => {
    if (typeof current !== "object" || current === null) {
      return undefined;
    }
    return current[part];
  }, tree);

  return typeof value === "string" ? value : null;
};

const formatMessage = (template: string, values?: Record<string, string | number>) => {
  if (!values) {
    return template;
  }

  return Object.entries(values).reduce(
    (result, [key, value]) => result.split(`{{${key}}}`).join(String(value)),
    template,
  );
};

export const LocaleProvider = ({ children }: PropsWithChildren) => {
  const [locale, setLocale] = useState<Locale>(() => {
    if (typeof window === "undefined") {
      return "en";
    }

    const storedLocale = window.localStorage.getItem(STORAGE_KEY);
    return storedLocale === "ko" ? "ko" : "en";
  });

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key, values) => {
        const message = resolveMessage(messages[locale], key) ?? resolveMessage(messages.en, key) ?? key;
        return formatMessage(message, values);
      },
    }),
    [locale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export const useI18n = () => {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within LocaleProvider");
  }
  return context;
};
