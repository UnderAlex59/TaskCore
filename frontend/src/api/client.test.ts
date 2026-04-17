import MockAdapter from "axios-mock-adapter";
import { afterEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/authStore";

describe("apiClient refresh queue", () => {
  const mock = new MockAdapter(apiClient);

  afterEach(() => {
    mock.reset();
    useAuthStore.setState({ user: null, accessToken: null, isInitialized: true });
  });

  it("refreshes once and retries queued requests", async () => {
    let refreshCalls = 0;
    useAuthStore.setState({ accessToken: "stale-token", user: null, isInitialized: true });

    mock.onPost("/auth/refresh").reply(() => {
      refreshCalls += 1;
      return [200, { access_token: "fresh-token", token_type: "bearer", expires_in: 900 }];
    });

    mock.onGet("/secure").reply((config) => {
      if (config.headers?.Authorization === "Bearer fresh-token") {
        return [200, { ok: true }];
      }
      return [401];
    });

    const [first, second] = await Promise.all([apiClient.get("/secure"), apiClient.get("/secure")]);

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(refreshCalls).toBe(1);
    expect(useAuthStore.getState().accessToken).toBe("fresh-token");
  });
});
