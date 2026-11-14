# MLS: what it is, how rental fakes ride it, and how SNAPBACK could plug in

Master Finder, goal snapback-mls, Fri Nov 13 2026, 21:15 to 21:22 EST. Builds on `plan/need-evidence.md` (Redfin Houston case, VERIFIED there) and `plan/costar-answers.md` (AB 723 statute, VERIFIED there); those facts are cited, not redone. States: VERIFIED = primary or named page read this run with the quote; REPORTED = search snippet or secondary only; UNRESOLVED = tried, not settled.

## Plain answer

1. **SF MLSs carry rentals, lots of them.** MLSListings shows 191 San Francisco rentals tonight, most with SFAR MLS numbers, each with an agent, broker and phone; a listing entered in SFAR MLS is auto-copied into MLSListings, BAREIS, Metrolist and Paragon. Portals then pull from those feeds.
2. **Fakes use the MLS two ways.** Clones: scammers copy a real MLS listing's photos or virtual tour, swap the contact, and repost it as a rental (FTC). Inside jobs: in Sep 2026 scammers took over a Pennsylvania agent's MLS account and posted fake rentals under his name; the Houston Redfin fake also entered through an MLS.
3. **MLSs already buy anti-fraud tools, from the agent's side.** SmartMLS (Connecticut) gives every member Property Shield's clone monitoring free, and is rolling out identity plus facial checks on would-be sellers (announced Nov 6 2026). None of these checks the renter's side, or compares the listing with the building itself. That is our gap.
4. **Our three sponsors are one company now, and realtors know it.** CoStar owns Homes.com, Apartments.com and Matterport, and on Oct 27 2026 agreed to buy Vexcel ($730M, closing Q1 2027). Realtors meet CoStar through Homes.com and Matterport tours, and the MLSs fight it over feeds: one MLS stopped accepting Homes.com-branded Matterport links, and the CRMLS data servicer sued CoStar over feed fees in 2025.
5. **Plugging in is possible but slow.** MLS data comes over the RESO Web API, but only after you sign that MLS's license. IDX is for brokers' sites; anyone else who earns money from the data pays (Homes.com reportedly about $2 a listing). The realistic pitch: the MLS buys SNAPBACK as a member benefit. It runs a building check when a rental is listed and sends clone alerts to the listing agent.
6. **Do not say:** "AB 723 adds an original-photo field." CRMLS put the unaltered photo next to the edited one in the listing. No MLS was found that adds an original-photo link field (NOT FOUND), and AB 723 covers sales only.

**Next step:** writer puts the 8 questions in section 5 on the realtor page tonight; Vidyut sends it to the two SF realtors.

## 1. What an MLS is in 2026 and how rentals move

- **What it is.** A multiple listing service is the shared database where member brokers enter listings and share them with each other. Its data travels by the RESO Web API: "MLSs owned and operated by REALTOR® associations are required by the National Association of REALTORS® to have production-level access available to their data via Web API" ([RESO Web API](https://www.reso.org/reso-web-api/), VERIFIED).
- **San Francisco.** SFAR runs SFARMLS. "Once a property is entered in SFARMLS, it is automatically duplicated in Paragon, MLSListings, BAREIS, and Metrolist" ([SFAR help, modified Jan 6 2026](https://sfar.freshdesk.com/support/solutions/articles/69000875631-how-do-i-list-a-property-on-another-mls-), VERIFIED).
- **SF MLSs carry rentals.** MLSListings' public search, fetched this run: "SAN FRANCISCO REAL ESTATE & HOMES FOR RENT: 191 RESULTS". The rows are condos, houses and commercial leases, most with `SF` MLS numbers (from SFAR), for example "1788 CLAY ST #501 ... $5,200 ... Condominium for Rent MLS #: SF426176395" with agent, broker and phone shown ([MLSListings SF rent](https://www.mlslistings.com/search/result/city/San%20Francisco/rent), VERIFIED). On the first page, 2 of 31 rows had a "VIRTUAL TOUR" badge (my count of that page only, not a rate).
- **Houston (HAR).** Rentals are a big MLS segment: "3,761 single-family homes were leased" in Sep 2026, and townhome/condo "active listings rose 8.8% to 2,456" ([HAR Rental Market Update, Oct 21 2026](https://www.har.com/content/department/rental_market_update), VERIFIED).
- **CRMLS and The MLS (LA).** Both appear in the industry fights below. Whether each carries lease listings, and how many, was NOT CHECKED (no time; MLSListings and HAR settle the "MLSs carry rentals" point).
- **Syndication to portals.**
  - Homes.com: "Homes.com receives a direct listing feed from the MLS" ([Homes.com support](https://www.homes.com/support/2022/07/18/where-does-homes-com-get-all-their-listings/), REPORTED: search snippet, the page timed out).
  - Apartments.com: "We work directly with hundreds of MLSs across the country" ([apartments.com/grow/mls](https://www.apartments.com/grow/mls), REPORTED: snippet, the page timed out).
  - ListHub, the syndicator, advertises "data feeds from 500+ MLSs" ([listhub.com](https://www.listhub.com/), REPORTED: snippet).
  - Redfin, Houston: the fake "came from a third-party multiple listing service (MLS), which then syndicated it to Redfin.com and several other websites" (VERIFIED in `need-evidence.md`, FOX 26, Aug 19 2026).
- **The MLS is no longer the only door.** Zillow's revised Listing Access Standards (Mar 17 2026) let a listing be "broadly accessible" without going on the MLS ([Real Estate News, Mar 19 2026](https://www.realestatenews.com/2026/03/19/zillows-simplified-listing-standards-make-the-mls-optional), VERIFIED). Compass sued 15 MLSs on Nov 12 2026, **including MLSListings**, over off-MLS marketing fines ([RISMedia, Nov 12 2026](https://www.rismedia.com/2026/11/12/compass-sues-15-mlss-8-states-marketing-restrictions/), VERIFIED). SF realtors will have opinions on both.

## 2. How scams exploit the MLS and syndication

| Pattern                                       | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | State              |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| **Clone a real listing and swap the contact** | FTC: "Scammers copy the pictures, description, or virtual tour from a real online rental listing, replace the agent's contact information with their own, and then post the phony ads on a new site." ([FTC, rev. Jun 2026](https://consumer.ftc.gov/articles/rental-listing-scams))                                                                                                                                                                                                        | VERIFIED           |
| **For-sale listing reposted as a rental**     | FTC: "if you find the home listed for sale instead of for rent, that's also a big red flag." The same page warns that self-tour door codes are copied too.                                                                                                                                                                                                                                                                                                                                  | VERIFIED           |
| **MLS account takeover, then fake rentals**   | PA Realtors, Sep 21 2026: a scammer emailed the MLS posing as a member, got the login email changed, took over the account and "began posting fake rental listings under the Realtor®'s name, requiring application fees, deposits and other payments." Two more associations reported the same. Advice: watch for "rentals posted by agents who have never posted rentals before." ([PAR blog](https://www.parealtors.org/blog/new-mls-scam-involves-gaining-access-to-members-accounts/)) | VERIFIED           |
| **Fake reaches portals through an MLS**       | Redfin Houston, $750 lost, lease and door code given (`need-evidence.md`, FOX 26)                                                                                                                                                                                                                                                                                                                                                                                                           | VERIFIED earlier   |
| **Seller impersonation (vacant land)**        | SmartMLS: "Ownership Verification is designed to help identify potential seller impersonation before a fraudulent listing enters the MLS" ([RISMedia, Nov 6 2026](https://www.rismedia.com/2026/11/06/smartmls-introduces-new-verification-tool-land-scams/))                                                                                                                                                                                                                               | VERIFIED           |
| MLS staff targeted by social engineering      | Council of MLS resource guide, Sep 2026 ([PDF](https://resources.councilofmls.org/wp-content/uploads/2026/09/Resource-Guide-Account-Change-Requests-and-Social-Engineering-Attempts-September-2026.pdf))                                                                                                                                                                                                                                                                                    | REPORTED (snippet) |

**MLS and association anti-fraud programs found**

- **SmartMLS plus Property Shield (CT).**
  - Listing fraud detection: the tool watches for people who "copy your listing data and photos and use them to create fake listing ads (usually rental ads) on social media". It offers "24/7 monitoring", alerts by email and a connectMLS widget, and takedowns "handled for you", at "No additional cost" to members ([connectMLS help, updated Nov 3 2026](https://connectmls.smartmls.com/hc/en-us/articles/57316573759771-Listing-fraud-detection), VERIFIED).
  - Ownership Verification: "identity verification and facial-recognition technology in conjunction with property ownership information" (RISMedia, above, VERIFIED).
  - REsides MLS was "the first MLS in the nation to offer Property Shield Ownership Verification", Jul 2026 ([RISMedia](https://www.rismedia.com/2026/07/16/resides-mls-launches-property-shield-ownership-verification/), REPORTED: snippet).
- **HAR (Houston).** The safety hub has a "Fake Rental Listings" video ("how scammers copy legitimate rental listings ... convince renters to send deposits before ever seeing a property"), a seller-impersonation flyer, a rental red-flags guide, and links to county deed-fraud alerts ([cms.har.com/safety](https://cms.har.com/safety/), VERIFIED). It offers education only; no listing monitoring was found on that page.
- **NAR.** Launched a fraud-fighting site on Sep 30 2026 ([NAR](https://www.nar.realtor/news/real-estate-news/new-nar-fraud-fighting-site-takes-aim-at-real-estate-scams), page fetched, body cut off before the content: REPORTED).
- **SFAR / MLSListings anti-fraud tool.** NOT FOUND (searched: "CRMLS rental listing fraud alert scam cloned listing" on Google, "MLSListings SFAR ... rentals" on Bing, Nov 13). This is a good thing to ask the realtors (Q3).

## 3. CoStar, Matterport and Vexcel versus MLSs and realtors

- **One owner.** CoStar's boilerplate lists Apartments.com, Homes.com and "Matterport, a leading spatial data company". On Oct 27 2026 it agreed to buy Vexcel "for approximately $730 million in cash"; Vexcel covers "99.6% of the U.S. Population", refreshes major US metros "up to three times a year", and the deal is "expected ... to close in the first quarter of 2027" ([CoStar release, Oct 27 2026](https://www.costargroup.com/press-room/2026/costar-group-acquire-vexcel-adding-worlds-largest-survey-grade-high-resolution), VERIFIED). Until it closes, Vexcel is a separate company, so say "soon to be CoStar".
- **Homes.com and the MLS feeds.** REcore, the CRMLS data servicer, sued CoStar on Oct 21 2025 over Homes.com's use of listing data, and the parties renewed their deal two days later. Inman: "Entities like real estate portals that monetize MLS data but don't represent buyers and sellers are required to pay for the data. Agents and brokers working with clients do not." According to REcore, Homes.com had agreed to pay "approximately $2 per listing displayed" ([Inman, Oct 23 2025](https://www.inman.com/2025/10/23/costar-reaches-agreement-with-crmls-keeping-access-to-data/), VERIFIED; the $2 is REcore's claim).
- **Homes.com versus Zillow.** CoStar filed an amicus brief against Zillow in Zillow v. MRED in June 2026, and the judge rejected it ([HousingWire](https://www.housingwire.com/articles/costar-zillow-mred-brief/), [Chicago Agent](https://chicagoagentmagazine.com/2026/06/16/judge-rejected-costars-brief-filed-in-zillow-mred-legal-battle/), REPORTED: snippets).
- **Matterport inside MLS listings.** MLS rules usually allow a tour only through an _unbranded_ virtual tour URL field. Realcomp (Michigan MLS), Feb 2026:
  - "Homes.com now owns Matterport and offers a membership program where agents receive a Matterport tour as part of their subscription ... These tours are branded".
  - "Realcomp will no longer accept virtual tours that include the Homes.com domain in the URL field". Agent- or photographer-made Matterport tours stay allowed with `&mls=1` added to the link ([Realcomp](https://www.realcomp.com/News-Events/Feature-2026/February-2026/-Matterport-Tours-Important-Update), VERIFIED).
  - MLSListings lets agents add both a branded and an unbranded tour ([MLSListings help](https://support.mlslistings.com/s/article/Add-a-Virtual-Tour), REPORTED: snippet).
  - How common Matterport tours are in MLS listings: NOT FOUND (one Bing query, "Matterport MLS integration virtual tour ... percent", Nov 13). The SF first-page count above (2 of 31 with any virtual tour) is not a rate.
- **Vexcel in MLS tools.** NOT FOUND (searched: "Vexcel imagery MLS real estate agents aerial imagery partnership MLS" on Bing; every result was the CoStar deal). Realtors probably do not know Vexcel by name (my inference, not checked).
- **Would SF realtors know these names?** Matterport: very likely, since it is a standard tour vendor (inference). CoStar: likely through Homes.com's agent ads and membership and the MLS feed fights (inference). Ask them (Q7).

## 4. Can SNAPBACK plug into the MLS?

- **Pipe.** RESO Web API (OData, REST). "Access to data from the Web API is gained through local MLSs. After agreeing to an MLS's data use and licensing policies, data recipients work directly with that MLS's software provider or technical staff to receive credentials" (RESO, VERIFIED).
- **License types.**
  - IDX: broker websites showing other brokers' listings.
  - VOW: a broker's logged-in client site.
  - Back office or data license: analytics and vendors.
  - Portals that monetize the data pay for it (Inman above).
  - Published prices vary. MLS PIN lists "A monthly access fee of $100" for broker data access ([MLS PIN](https://www.mlspin.com/resources/data-services), REPORTED: snippet). Industry guides quote $100 to $2,000+ a month (REPORTED, tier 4, low trust).
  - SFAR's or MLSListings' vendor fee and approval time: UNRESOLVED (needs their data licensing page or a call).
- **What we cannot do tonight.** We have no MLS license, so the hackathon build uses the CoStar kit only and must not scrape MLS or portal pages. An MLS integration stays a pitch, never a claim.
- **Badges or verify links on listings.** Most MLSs ban links and contact details in public remarks and allow only unbranded tours in the tour field (Realcomp quote above shows the pattern). Whether SFAR would allow a "Verified by SNAPBACK" link in any field: UNRESOLVED; ask (Q5).
- **AB 723 and an original-photo field.** CRMLS Rule 11.5.2 requires the subscriber to "submit the original, unaltered version" and display it "immediately before or after the digitally altered image", labelled "Photo Modified", "Virtually Staged", "Digitally Altered" or "AI Altered" in the photo's text field. There is no fine yet: "the CRMLS Rules Committee will revisit the matter of fines in 2026" ([CRMLS FAQ PDF, updated Feb 13 2026](https://go.crmls.org/wp-content/uploads/2026/02/2026_Digitally_Altered_Images_FAQs_v1.pdf), VERIFIED). So the original lives in the photo set, not in a URL field. NOT FOUND for any MLS adding an "unaltered photo URL" field (searched "CRMLS AB 723 altered photo field unaltered image MLS" on Bing). MLSListings' AB 723 article needs JavaScript and was not read (UNRESOLVED). AB 723 covers sales by licensees only, not rentals (`costar-answers.md`, VERIFIED).
- **A realistic pitch to an MLS (bold version first).**
  1. **"Verified at listing" for rentals.** When an agent saves a lease listing, SNAPBACK checks the address against the CoStar building record, the unit's floor plan against the Matterport twin and the photos against Vexcel aerials. It then registers a fingerprint of the photo set. Wrong building, a for-sale listing re-entered as a rental, or a first rental from an agent who has never listed one (the PA takeover sign) goes to MLS compliance before syndication. Buyer: the MLS, as a member benefit, the way SmartMLS buys Property Shield.
  2. **Clone alerts to the listing agent.** When a renter forwards a listing to SNAPBACK and its photos match a registered MLS listing with a different contact or price, the listing agent gets an alert. This overlaps with Property Shield (social-media monitoring). Our difference: the renter brings the clone to us at the moment of payment, so we do not depend on crawling.
  3. **Safer first step:** a renter-side check only, with no MLS data. Agents and MLSs get a public "check this listing" link they can send renters. This needs no license.
  - Every recommendation above depends on two UNRESOLVED facts: the MLS's license terms for a fraud-check vendor, and CoStar letting us use the kit data beyond the hackathon (`costar-answers.md` q1 and q6).

## 5. Questions for the SF realtors (for the realtor page)

1. Do you list rentals in SFAR MLS? About what share of your listings are leases, and who usually asks you to list them?
2. Has one of your listings, sale or rental, ever been copied into a fake rental ad? How did you find out, and how long did it take to get it taken down?
3. Does SFAR or MLSListings give you any clone or fraud alert today? If a tool told you within an hour that your listing was copied, what would you do with that alert?
4. Have you seen a for-sale listing of yours reposted as a rental, or a rental posted under an agent's name by someone who took over their MLS login?
5. If the MLS let a rental listing carry a "Verified: this matches the building's records" mark, would you want it, or would it feel like one more compliance box? Who should pay: you, your broker or the MLS?
6. When renters ask you whether a listing is real, what do you tell them to check? What do they get wrong?
7. Do you use Matterport tours on your listings? Do you think of Matterport, Homes.com and Apartments.com as one company (CoStar)? Does that change whether you would trust a check built on their data?
8. AB 723 now makes you show the unaltered photo when you edit a sale photo. Should rentals get the same rule? Would you use a tool that flags edited or reused rental photos before you list?

## What this means / what to do

- Pitch line that will land with realtors: "A thief can copy your MLS photos or steal your login. SNAPBACK checks the listing against the building itself, and tells you when a clone of your listing shows up."
- Treat Property Shield (in SmartMLS and REsides) as the incumbent on the MLS side, and name it on the page. Our angle is the building check at the moment the renter pays, not crawling for copies.
- Keep Vexcel as "soon to be CoStar (deal announced Oct 27 2026)".

## Not checked

- CRMLS and The MLS (LA) rental volumes and their fraud programs; Bright MLS programs (no time).
- SFAR and MLSListings data-license fees, vendor approval steps and listing-field rules (need their licensing pages or a call).
- How common Matterport tours are in MLS listings (no stat found).
- The full text of NAR's fraud site and of the Council of MLS guide (pages cut off or not opened).

## Sources (all fetched this run between 21:16 and 21:20 EST, Nov 13 2026)

SFAR help · SmartMLS connectMLS help · RISMedia SmartMLS Nov 6 · HAR safety · CRMLS AB 723 FAQ PDF (HTTP 200) · MLSListings SF rent search · Real Estate News Zillow LAS · CoStar Vexcel release · PAR MLS account scam · Realcomp Matterport · RESO Web API · Inman CoStar CRMLS · RISMedia Compass suits · HAR rental update · FTC rental listing scams. The URLs are inline above.

GOAL: snapback-mls met · due 22:05 EST · finished 21:22 EST
COST: 22/25-40 searches+fetches (7 search batches counted as 1 each, 15 page fetches) · 4 files read · 6 runs · 0 sub-agents · workers 0 · Bright Data about 35 requests (free tier)

CHECKED_AT: Fri Nov 13 2026, 21:15 to 21:22 EST
SUBJECT: plan/mls.md (research doc, no repo SHA)
CHECKED: the URLs above, plan/need-evidence.md, plan/costar-answers.md, plan/decisions.md (grep)
NOT CHECKED: see the "Not checked" list
UNRESOLVED: SFAR or MLSListings vendor license cost and rules on a verify link or badge (settle by calling SFAR MLS support); the MLSListings AB 723 article (needs JavaScript); the Homes.com and Apartments.com MLS-feed pages (timed out, snippets only)
