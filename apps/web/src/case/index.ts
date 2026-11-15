// The case result pieces (design v4 ticket 3). The case page and the Home thread build from
// the same ones.
export { AnnotatedAd, markRuns } from "./AnnotatedAd";
export { Checks } from "./Checks";
export { CaseResult, type CaseResultProps } from "./CaseResult";
export { Ledger, groupLines, type LedgerGroup } from "./Ledger";
export {
  VERDICT_TONE,
  checkCount,
  checkedStamp,
  expiryText,
  flaggedLines,
  photosPlaced,
  recordSourceOf,
  stateKind,
  hostLink,
  outLink,
  type AdMark,
  type PriceFigures,
  type ProofData,
  type ProofPin,
  type ProofShot,
  couldNotDo,
  missingFact,
  withoutPhoneDigits,
  type CopyAlert,
  type RealListing as RealListingData,
  type RealListingPlan,
  type ReportPack,
  type SaferPlace,
  type VerdictTone,
} from "./model";
export {
  APARTMENTS_SEARCH,
  DraftedStep,
  NextSteps,
  caseSteps,
  draftedStep,
  type NextStep,
} from "./NextSteps";
export { PlannerChoice, plannerChoices } from "./PlannerChoice";
export { PriceBar, priceScale } from "./PriceBar";
export { ProofPair, stampPlace } from "./ProofPair";
export { RealListing, realListingLink } from "./RealListing";
export { SaferTiles, saferTiles } from "./SaferTiles";
export { StillChecking } from "./StillChecking";
export { useProof, useProofRead } from "./useProof";
export {
  useCopyAlert,
  useCopyAlertRead,
  useRealListing,
  useRealListingRead,
  useReportPack,
  useReportPackRead,
  useSaferPlaces,
  useSaferPlacesRead,
  useTimeline,
  type Read,
} from "./useProofApi";
export { AnswerPanel } from "./AnswerPanel";
export { answerView, checkOfReason, reasonLines, tookText } from "./answer";
export { VerdictBand, type BandAction } from "./VerdictBand";
export { AGENCIES, AlertDraft, FilePanel, WhatNext, reportText } from "./WhatNext";
export { openTimelineStream } from "./useTimelineStream";
