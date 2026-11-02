# The online service

Online play (`runtime/sc2_netplay.h`) is two copies of the game sending each other their players' controls
directly. This service only introduces them: a host asks it for a code; the other player gives the code, and each is
told where the other can be reached. Nothing of a match goes through it. It is a
[Cloudflare Worker](https://developers.cloudflare.com/workers/) with a Durable Object for each match
(`src/index.js`), within Cloudflare's free plan. It is cps2recomp's (`online/` there, which has the details of how
the two meet, the lobby and the waiting room), deployed on its own for Soulcalibur II.

## Running it

```sh
cd online
npx wrangler login     # once: Cloudflare's tool, signed in to the account in a browser
npx wrangler deploy    # https://soulcalibur2-online.<the account's subdomain>.workers.dev
npx wrangler secret put STATS_KEY   # once, for the stats page (GET /v1/stats?key=KEY)
```

The game asks `Netplay::kService` (`runtime/sc2_netplay.h`) unless started with `--net-service URL` (or `off`:
addresses only); the launcher's lobby is the same service's `/v1/lobby/soulcalibur2`.
