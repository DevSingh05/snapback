import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import zelleFixture from "../replay/fixtures/zelle-deposit-copied-tour.json";
import { registerTestReplays } from "../replay";
import type { Replay } from "../replay/types";

registerTestReplays([zelleFixture as Replay]);

afterEach(() => cleanup());
