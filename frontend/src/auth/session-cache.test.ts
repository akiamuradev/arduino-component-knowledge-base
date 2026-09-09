import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import type { User } from "../api/contracts";
import { createQueryClient } from "../app/query-client";
import { currentUserQueryKey, replaceSessionCache } from "./session-cache";

const student: User = {
  id: "student-id", login: "student", display_name: "Student",
  roles: ["student"], permissions: ["components.view"],
};

describe("session cache ownership", () => {
  it("replaces administrator data with only the next identity", async () => {
    const client = createQueryClient();
    client.setQueryData(currentUserQueryKey, { ...student, id: "admin-id", roles: ["administrator"] });
    client.setQueryData(["workspace", "components"], ["private draft"]);
    client.setQueryData(["admin", "users"], ["private user"]);
    client.getMutationCache().build(client, { mutationKey: ["save"] });
    await replaceSessionCache(client, student);
    expect(client.getQueryData(currentUserQueryKey)).toEqual(student);
    expect(client.getQueryCache().getAll().map(query => query.queryKey)).toEqual([currentUserQueryKey]);
    expect(client.getMutationCache().getAll()).toEqual([]);
    client.clear();
  });

  it("does not restore private data when a cancelled request ignores AbortSignal", async () => {
    const client = createQueryClient();
    let resolve: (value: string[]) => void = () => { throw new Error("request not started"); };
    const deferred = new Promise<string[]>(done => { resolve = done; });
    const request = client.query({ queryKey: ["workspace"], queryFn: () => deferred });
    const cancelled = request.catch(() => undefined);
    await replaceSessionCache(client, student);
    resolve(["late private draft"]);
    await cancelled;
    await deferred;
    expect(client.getQueryData(["workspace"])).toBeUndefined();
    expect(client.getQueryData(currentUserQueryKey)).toEqual(student);
    client.clear();
  });

  it("clears all cached queries on logout", async () => {
    const client = createQueryClient();
    client.setQueryData(currentUserQueryKey, student);
    client.setQueryData(["catalog"], ["cached card"]);
    await replaceSessionCache(client);
    expect(client.getQueryCache().getAll()).toEqual([]);
  });

  it("retains the auth error for guards but removes private data on session expiry", async () => {
    const client = createQueryClient();
    client.setQueryData(["workspace"], ["private draft"]);
    const error = new ApiError(401, "authentication_required");
    await expect(client.query({
      queryKey: currentUserQueryKey,
      queryFn: () => Promise.reject(error), retry: false,
    })).rejects.toBe(error);
    await Promise.resolve();
    expect(client.getQueryData(["workspace"])).toBeUndefined();
    expect(client.getQueryState(currentUserQueryKey)?.error).toBe(error);
    client.clear();
  });

  it("does not treat permission denial as session expiry", async () => {
    const client = createQueryClient();
    client.setQueryData(currentUserQueryKey, student);
    const error = new ApiError(403, "permission_denied");
    await expect(client.query({
      queryKey: ["admin"], queryFn: () => Promise.reject(error), retry: false,
    })).rejects.toBe(error);
    expect(client.getQueryData(currentUserQueryKey)).toEqual(student);
    client.clear();
  });
});
