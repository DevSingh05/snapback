import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { PROFILE_TTL_MS, ProfileStore, learnFrom, profileCommand } from "./profile";

const KEY = "imsg-0123456789abcdef01234567";

// --- learning from what the renter says about themselves -------------------------------------

test("Spanish is learned from a message written in Spanish", () => {
  assert.equal(learnFrom("Hola, busco un departamento de 2 recámaras, ¿es real?").lang, "es");
  assert.equal(learnFrom("Hi, is this listing real? I want to rent it.").lang, "en");
  assert.equal(learnFrom("ok").lang, undefined, "too short to tell");
});

test("budget and beds are learned only from the renter's own words, never an ad's rent", () => {
  assert.deepEqual(learnFrom("My budget is $1,500 and I need 2 beds"), {
    lang: "en",
    budget: 1500,
    beds: 2,
  });
  assert.equal(learnFrom("I can pay up to 1800 a month").budget, 1800);
  assert.equal(learnFrom("looking for a 3 bedroom").beds, 3);
  // an ad's own rent and beds are not the renter's budget
  const ad = learnFrom("2 bed / 2 bath apartment, $1,150 a month, Zelle the deposit");
  assert.equal(ad.budget, undefined);
  assert.equal(ad.beds, undefined);
  assert.equal(learnFrom("Mi presupuesto es $1,200 y necesito 2 recámaras").budget, 1200);
  assert.equal(learnFrom("Mi presupuesto es $1,200 y necesito 2 recámaras").beds, 2);
});

test("a city is learned when the renter says where they are moving or looking", () => {
  assert.equal(learnFrom("I'm moving to Houston in January").city, "Houston");
  assert.equal(learnFrom("looking in Dallas").city, "Dallas");
  assert.equal(
    learnFrom("Houston apartment for rent, 2 bed").city,
    undefined,
    "an ad's city is not the renter's",
  );
});

// --- the store -----------------------------------------------------------------------------------

test("the store merges what it learns, keyed only by the keyed hash", () => {
  const store = new ProfileStore();
  store.learn(KEY, "My budget is $1,500");
  store.learn(KEY, "I need 2 beds");
  assert.deepEqual(store.get(KEY), { lang: "en", budget: 1500, beds: 2 });
  assert.equal(store.get("+17135550142"), null);
});

test("a profile expires after 30 days", () => {
  let now = Date.parse("2026-11-14T12:00:00Z");
  const store = new ProfileStore(undefined, () => now);
  store.learn(KEY, "My budget is $1,500");
  now += PROFILE_TTL_MS + 1;
  assert.equal(store.get(KEY), null);
});

test("'forget me' wipes the profile, in memory and on disk", () => {
  const dir = mkdtempSync(join(tmpdir(), "snapback-profile-"));
  const file = join(dir, "profiles.json");
  const store = new ProfileStore(file);
  store.learn(KEY, "My budget is $1,500 and I need 2 beds");
  assert.match(readFileSync(file, "utf8"), /1500/);
  store.forget(KEY);
  assert.equal(store.get(KEY), null);
  assert.doesNotMatch(readFileSync(file, "utf8"), /1500/);
});

test("the file holds only the keyed hash and the learned fields, never words or numbers of a phone", () => {
  const dir = mkdtempSync(join(tmpdir(), "snapback-profile-"));
  const file = join(dir, "profiles.json");
  const store = new ProfileStore(file);
  store.learn(KEY, "My budget is $1,500. Call me at 555-0142, I'm moving to Houston");
  const saved = readFileSync(file, "utf8");
  assert.ok(saved.includes(KEY));
  assert.doesNotMatch(saved, /555|Call me/);
  // a new store reads it back
  assert.equal(new ProfileStore(file).get(KEY)?.budget, 1500);
});

test("a missing or broken file starts empty, never crashes", () => {
  const dir = mkdtempSync(join(tmpdir(), "snapback-profile-"));
  assert.equal(new ProfileStore(join(dir, "none.json")).get(KEY), null);
  assert.equal(existsSync(join(dir, "none.json")), false);
});

// --- commands --------------------------------------------------------------------------------------

test("'what do you remember?' lists what is kept, in the renter's language", () => {
  const store = new ProfileStore();
  store.learn(KEY, "My budget is $1,500 and I need 2 beds, moving to Houston");
  const said = profileCommand("What do you remember?", KEY, store);
  assert.match(said ?? "", /budget: \$1,500/);
  assert.match(said ?? "", /beds: 2/);
  assert.match(said ?? "", /city: Houston/);
  assert.match(said ?? "", /forget me/);
  const es = new ProfileStore();
  es.learn(KEY, "Hola, mi presupuesto es $1,200 y necesito 2 recámaras");
  assert.match(profileCommand("¿qué recuerdas?", KEY, es) ?? "", /presupuesto: \$1,200/);
});

test("'what do you remember?' with nothing kept says so", () => {
  assert.match(profileCommand("what do you remember", KEY, new ProfileStore()) ?? "", /nothing/i);
});

test("'forget me' wipes it and says so; other text is not a command", () => {
  const store = new ProfileStore();
  store.learn(KEY, "My budget is $1,500");
  assert.match(profileCommand("forget me", KEY, store) ?? "", /forgot/i);
  assert.equal(store.get(KEY), null);
  assert.equal(profileCommand("2 bed $900 Zelle first", KEY, store), null);
});
