// The case result pieces (design v4 ticket 3). The case page and the Home thread build from
// the same ones.
export { AnnotatedAd, markRuns } from "./AnnotatedAd";
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
  type ProofCard,
  type ProofData,
  type ProofPin,
  type ProofShot,
  type RealListing as RealListingData,
  type RealListingPlan,
  type SaferPlace,
  type VerdictTone,
} from "./model";
export { APARTMENTS_SEARCH, NextSteps, caseSteps, type NextStep } from "./NextSteps";
export { PriceBar, priceScale } from "./PriceBar";
export { ProofPair, stampPlace } from "./ProofPair";
export { RealListing, realListingLink } from "./RealListing";
export { SaferTiles, saferTiles } from "./SaferTiles";
export { useProof } from "./useProof";
export { useRealListing, useSaferPlaces } from "./useProofApi";
export { VerdictBand, type BandAction } from "./VerdictBand";
