"""The HTTP client every simulated person acts through.

Deliberately thin, and built on ``httpx`` — already a dev dependency of this
project (``manage.py load_rehearsal`` needs it), so the stress test adds none
of its own. Each simulated person gets their **own** ``Api``: their own
connection pool, their own JWT, their own cookie jar for the refresh cookie
the API never puts in a response body. That is what makes 80 of them look
like 80 clients to the ingress rather than one very busy one.

Four things it does that raw ``httpx`` doesn't:

* unwraps the ``{"data": ...}`` envelope every successful response is rendered
  in (``apps.core_common.renderers``) and raises :class:`ApiError` carrying
  the ``{"error": ...}`` body otherwise;
* times every call into :class:`~stress.src.metrics.Metrics` under a coarse
  label, failures included — a stress run that quietly swallowed its 500s
  would be measuring nothing;
* **waits out a 429 rather than failing it.** Signing up is on the ``login``
  throttle scope (10/min per IP by default), and 80 accounts from one machine
  will meet it. A throttle refusing the 11th signup in a minute is the
  platform working; counting it as a failure would bury the failures that
  aren't;
* re-authenticates on a 401, because a long run outlives the 30-minute access
  token — through the refresh cookie first (``POST /auth/token/refresh/``,
  which is only on the ``anon`` ceiling), falling back to a full sign-in.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx

from .metrics import Metrics


class ApiError(RuntimeError):
    """A non-2xx answer. Carries enough to decide what to do about it —
    callers branch on ``status``."""

    def __init__(self, *, status: int, method: str, path: str, body: Any) -> None:
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"{method} {path} → {status}: {_detail(body)}")

    @property
    def code(self) -> str:
        """The domain error code, when the envelope carried one
        (``apps.core_common.exceptions.DomainError``)."""
        if isinstance(self.body, dict):
            error = self.body.get("error")
            if isinstance(error, dict):
                return str(error.get("code", ""))
        return ""


class Api:
    """One caller's session against the API."""

    def __init__(
        self,
        *,
        base_url: str,
        metrics: Metrics,
        verify: bool = False,
        timeout: float = 30.0,
        max_retries: int = 12,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.metrics = metrics
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            base_url=self.base_url, verify=verify, timeout=timeout, follow_redirects=True
        )
        self.access: str | None = None
        #: Set by :meth:`register`/:meth:`login` so a 401 mid-run can be
        #: answered without the caller having to hold the credentials itself.
        self.email: str | None = None
        self.password: str | None = None

    async def aclose(self) -> None:
        await self.client.aclose()

    # --- auth ---------------------------------------------------------------

    async def register(self, *, email: str, password: str) -> dict:
        """Sign up — an email and a password, which is the whole form
        (``apps.accounts.api.views.RegisterView``). The endpoint answers with
        the access token, so a fresh account is usable without a second round
        trip; the refresh half is set as an HttpOnly cookie and stays in this
        client's jar. The display name is claimed after, through
        ``PATCH /players/me/``, exactly as the SPA's welcome screen does it.

        The email is also how a stress run tags its own rows —
        ``purge_stress`` finds them by the ``@stress.knowdown.test`` domain,
        so the generated addresses have to stay on that domain or teardown
        misses them.
        """
        data = await self.post(
            "/api/v1/auth/registration/",
            json={"email": email, "password1": password, "password2": password},
            label="register",
            auth=False,
        )
        self.email, self.password = email, password
        self.access = data.get("access") or self.access
        return data

    async def login(self, *, email: str, password: str) -> dict:
        data = await self.post(
            "/api/v1/auth/token/",
            json={"email": email, "password": password},
            label="login",
            auth=False,
        )
        self.email, self.password = email, password
        self.access = data.get("access") or self.access
        return data

    async def reauthenticate(self) -> bool:
        """Get a usable access token back, cheapest door first.

        The refresh cookie is on the ordinary ``anon`` ceiling; a full
        sign-in is on ``login``'s much tighter one, which 80 clients hitting
        at once would exhaust in seconds. So: rotate if we can, sign in only
        if we must.
        """
        try:
            data = await self.post(
                "/api/v1/auth/token/refresh/", json={}, label="refresh", auth=False
            )
            self.access = data.get("access") or self.access
            return bool(self.access)
        except ApiError:
            pass
        if not (self.email and self.password):
            return False
        try:
            await self.login(email=self.email, password=self.password)
            return True
        except ApiError:
            return False

    def adopt(self, *, email: str, password: str, access: str, refresh: str | None) -> None:
        """Take a token seeding already obtained, without paying for a login.

        The refresh token goes back into the cookie jar it came out of —
        ``apps.accounts`` never reads it from a body — so a run started long
        enough after its seed to have an expired access token can rotate
        rather than sign 80 accounts in against a 10/min door.
        """
        self.email, self.password = email, password
        self.access = access
        if refresh:
            self.client.cookies.set(
                "knowdown_refresh", refresh, domain=httpx.URL(self.base_url).host
            )

    @property
    def refresh_cookie(self) -> str | None:
        return self.client.cookies.get("knowdown_refresh")

    # --- verbs --------------------------------------------------------------

    async def get(self, path: str, **kwargs) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> Any:
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> Any:
        return await self.request("PATCH", path, **kwargs)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        label: str | None = None,
        auth: bool = True,
        retry_auth: bool = True,
        benign: tuple[int, ...] = (),
    ) -> Any:
        label = label or f"{method.lower()} {path}"

        for attempt in range(self.max_retries + 1):
            headers = {}
            if auth and self.access:
                headers["Authorization"] = f"Bearer {self.access}"

            started = time.monotonic()
            try:
                response = await self.client.request(
                    method, path, json=json, params=params, headers=headers
                )
            except httpx.HTTPError as exc:
                # A refused connection or a timeout *is* a result under load —
                # the kind this test is watching for — so it is recorded like
                # any other failure rather than vanishing into a traceback.
                self.metrics.record(
                    label=label,
                    seconds=time.monotonic() - started,
                    ok=False,
                    status=type(exc).__name__,
                )
                raise ApiError(
                    status=0, method=method, path=path, body={"error": str(exc)}
                ) from exc

            elapsed = time.monotonic() - started
            ok = response.status_code < 400
            self.metrics.record(
                label=label,
                seconds=elapsed,
                ok=ok,
                status=str(response.status_code),
                benign=response.status_code in benign
                or response.status_code == httpx.codes.TOO_MANY_REQUESTS,
            )

            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(_retry_after(response))
                continue

            if response.status_code == 401 and auth and retry_auth:
                # The access token expired under a long run. One re-auth,
                # then the call again — and if that fails too it fails for
                # real.
                if await self.reauthenticate():
                    return await self.request(
                        method, path, json=json, params=params, label=label,
                        auth=auth, retry_auth=False, benign=benign,
                    )

            body = _body(response)
            if not ok:
                raise ApiError(
                    status=response.status_code, method=method, path=path, body=body
                )
            if isinstance(body, dict) and "data" in body:
                return body["data"]
            return body

        raise ApiError(
            status=429,
            method=method,
            path=path,
            body={"error": f"still throttled after {self.max_retries} retries"},
        )


def _retry_after(response: httpx.Response) -> float:
    """How long to wait before trying a throttled call again.

    DRF sends ``Retry-After`` in whole seconds; the jitter on top is what
    keeps 80 clients that were all refused in the same second from all
    returning in the same second too.
    """
    header = response.headers.get("Retry-After", "")
    try:
        base = float(header)
    except ValueError:
        base = 5.0
    return min(base, 120.0) + random.uniform(0, 1.5)


def _body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"error": response.text[:400]}


def _detail(body: Any) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("detail") or error)
        if error:
            return str(error)
    return str(body)[:300]
