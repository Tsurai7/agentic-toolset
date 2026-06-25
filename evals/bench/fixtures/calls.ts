// Fixture for the ast-grep precision benchmark.
// TRUE call sites of fetchUser(...): there are exactly 4 below.
// Decoys that a regex `fetchUser(` would wrongly catch: the definition, a comment,
// a string literal, and the different identifier `prefetchUser(`.

export function fetchUser(id: string) {        // decoy: definition, not a call
  return db.users.get(id);
}

function prefetchUser(id: string) {            // decoy: different identifier
  return cache.warm(id);
}

async function loadProfile(id: string) {
  const u = await fetchUser(id);               // TRUE call 1
  return u;
}

function loadDashboard(ids: string[]) {
  const a = fetchUser(ids[0]);                 // TRUE call 2
  const b = fetchUser(ids[1]);                 // TRUE call 3
  return [a, b];
}

// Remember to call fetchUser(id) before rendering.   // decoy: comment
const help = "use fetchUser(id) to load";             // decoy: string literal

export function refresh(id: string) {
  prefetchUser(id);                            // decoy call: different function
  return fetchUser(id);                        // TRUE call 4
}
