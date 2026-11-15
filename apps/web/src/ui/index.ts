// The shared primitives every screen builds from (design v4 ticket 0).
export { ChapterStrip, chapterColumns, type Chapter } from "./ChapterStrip";
export { EmptyRows } from "./EmptyRows";
export { Loading } from "./Loading";
export { DEFAULT_MARK, Lockup, MARK_PATHS, Mark, type MarkVariant } from "./Mark";
export { PATH_STEPS, PathRail, type PathStep } from "./PathRail";
export { Photo, PhotoPin, STAMP_TEXT, type StampKind } from "./Photo";
export { photoFor, type ChosenPhoto, type PhotoSources } from "./photoFor";
export { Problem } from "./Problem";
export { RECORD_SOURCE, RecordLine, recordLineText, type RecordSource } from "./RecordLine";
export { STATE_LABEL, State, type StateKind } from "./State";
export type { StateAction } from "./states";
export { STOCK, type StockKind, type StockPhoto } from "./stock";
export { TAG_HINT, Tag } from "./Tag";
