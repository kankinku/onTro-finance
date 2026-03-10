import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { CouncilAskPage } from "../routes/CouncilAskPage";
import { DataIntakePage } from "../routes/DataIntakePage";
import { GraphExplorerPage } from "../routes/GraphExplorerPage";
import { OverviewPage } from "../routes/OverviewPage";
import { SavedDataPage } from "../routes/SavedDataPage";
import { ConsoleLayout } from "./ConsoleLayout";
import { createQueryClient } from "./create-query-client";

export const App = () => {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route element={<ConsoleLayout />} path="/">
          <Route element={<OverviewPage />} index />
          <Route element={<DataIntakePage />} path="intake" />
          <Route element={<SavedDataPage />} path="saved" />
          <Route element={<GraphExplorerPage />} path="graph" />
          <Route element={<CouncilAskPage />} path="council" />
        </Route>
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </QueryClientProvider>
  );
};
