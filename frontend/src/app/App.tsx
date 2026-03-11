import { QueryClientProvider } from "@tanstack/react-query";
import { Suspense, lazy, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { ConsoleLayout } from "./ConsoleLayout";
import { createQueryClient } from "./create-query-client";
import { LocaleProvider } from "./i18n";

const OverviewPage = lazy(async () => import("../routes/OverviewPage").then((module) => ({ default: module.OverviewPage })));
const DataIntakePage = lazy(async () => import("../routes/DataIntakePage").then((module) => ({ default: module.DataIntakePage })));
const SavedDataPage = lazy(async () => import("../routes/SavedDataPage").then((module) => ({ default: module.SavedDataPage })));
const GraphExplorerPage = lazy(async () => import("../routes/GraphExplorerPage").then((module) => ({ default: module.GraphExplorerPage })));
const CouncilAskPage = lazy(async () => import("../routes/CouncilAskPage").then((module) => ({ default: module.CouncilAskPage })));
const LearningDetailPage = lazy(async () => import("../routes/LearningDetailPage").then((module) => ({ default: module.LearningDetailPage })));

export const App = () => {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <Suspense fallback={<div className="page-stack"><p className="empty-state">Loading...</p></div>}>
          <Routes>
            <Route element={<ConsoleLayout />} path="/">
              <Route element={<OverviewPage />} index />
              <Route element={<DataIntakePage />} path="intake" />
              <Route element={<SavedDataPage />} path="saved" />
              <Route element={<GraphExplorerPage />} path="graph" />
              <Route element={<CouncilAskPage />} path="council" />
              <Route element={<LearningDetailPage />} path="learning/:kind/:fileName" />
            </Route>
            <Route element={<Navigate replace to="/" />} path="*" />
          </Routes>
        </Suspense>
      </LocaleProvider>
    </QueryClientProvider>
  );
};
