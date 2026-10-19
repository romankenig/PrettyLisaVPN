import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
afterEach(cleanup);

import { languagePreference } from "../i18n/language";
beforeEach(() => languagePreference.choose("ru"));
