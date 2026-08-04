export interface SCIMUserMeta {
  resourceType: "User";
  created: string;
  lastModified: string;
  location: string;
}

export interface SCIMUserResource {
  schemas: string[];
  id: string;
  externalId?: string;
  userName: string;
  name?: { formatted?: string; givenName?: string; familyName?: string };
  emails?: Array<{ value: string; primary?: boolean; type?: string }>;
  active: boolean;
  groups?: Array<{ value: string; display: string }>;
  meta: SCIMUserMeta;
}

export interface SCIMListResponse<T> {
  schemas: ["urn:ietf:params:scim:api:messages:2.0:ListResponse"];
  totalResults: number;
  itemsPerPage: number;
  startIndex: number;
  Resources: T[];
}

export interface SCIMGroupResource {
  schemas: string[];
  id: string;
  displayName: string;
  members?: Array<{ value: string; display?: string }>;
  meta: {
    resourceType: "Group";
    created: string;
    lastModified: string;
    location: string;
  };
}

export class SCIMDirectoryService {
  private users: Map<string, SCIMUserResource> = new Map();
  private groups: Map<string, SCIMGroupResource> = new Map();

  constructor() {
    // Seed default admin group
    this.groups.set("group-admin", {
      schemas: ["urn:ietf:params:scim:schemas:core:2.0:Group"],
      id: "group-admin",
      displayName: "Administrators",
      members: [],
      meta: {
        resourceType: "Group",
        created: new Date().toISOString(),
        lastModified: new Date().toISOString(),
        location: "/scim/v2/Groups/group-admin",
      },
    });
  }

  public getUsers(filter?: string, startIndex: number = 1, count: number = 20): SCIMListResponse<SCIMUserResource> {
    let all = Array.from(this.users.values());

    if (filter) {
      const matchName = filter.match(/userName eq "([^"]+)"/i);
      const matchExt = filter.match(/externalId eq "([^"]+)"/i);

      if (matchName) {
        const userName = matchName[1];
        all = all.filter((u) => u.userName.toLowerCase() === userName.toLowerCase());
      } else if (matchExt) {
        const extId = matchExt[1];
        all = all.filter((u) => u.externalId === extId);
      }
    }

    const totalResults = all.length;
    const paged = all.slice(startIndex - 1, startIndex - 1 + count);

    return {
      schemas: ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
      totalResults,
      itemsPerPage: paged.length,
      startIndex,
      Resources: paged,
    };
  }

  public getUserById(id: string): SCIMUserResource | null {
    return this.users.get(id) || null;
  }

  public createUser(payload: any): SCIMUserResource {
    const id = payload.id || `scim-usr-${Math.random().toString(36).substring(2, 10)}`;
    const now = new Date().toISOString();

    const resource: SCIMUserResource = {
      schemas: ["urn:ietf:params:scim:schemas:core:2.0:User"],
      id,
      externalId: payload.externalId,
      userName: payload.userName,
      name: payload.name || { formatted: payload.userName },
      emails: payload.emails || [],
      active: payload.active !== undefined ? Boolean(payload.active) : true,
      groups: payload.groups || [],
      meta: {
        resourceType: "User",
        created: now,
        lastModified: now,
        location: `/scim/v2/Users/${id}`,
      },
    };

    this.users.set(id, resource);
    return resource;
  }

  public updateUser(id: string, payload: any): SCIMUserResource {
    const existing = this.users.get(id);
    if (!existing) {
      throw new Error(`404: User ${id} not found`);
    }

    const now = new Date().toISOString();
    const updated: SCIMUserResource = {
      ...existing,
      userName: payload.userName || existing.userName,
      externalId: payload.externalId !== undefined ? payload.externalId : existing.externalId,
      name: payload.name || existing.name,
      emails: payload.emails || existing.emails,
      active: payload.active !== undefined ? Boolean(payload.active) : existing.active,
      meta: {
        ...existing.meta,
        lastModified: now,
      },
    };

    this.users.set(id, updated);
    return updated;
  }

  public patchUser(id: string, operations: Array<{ op: string; path?: string; value: any }>): SCIMUserResource {
    const existing = this.users.get(id);
    if (!existing) {
      throw new Error(`404: User ${id} not found`);
    }

    for (const op of operations) {
      if (op.op.toLowerCase() === "replace") {
        if (op.path === "active" || op.value?.active !== undefined) {
          existing.active = Boolean(op.path === "active" ? op.value : op.value.active);
        }
        if (op.path === "userName" || op.value?.userName) {
          existing.userName = op.path === "userName" ? op.value : op.value.userName;
        }
      }
    }

    existing.meta.lastModified = new Date().toISOString();
    this.users.set(id, existing);
    return existing;
  }

  public deactivateUser(id: string): void {
    const existing = this.users.get(id);
    if (!existing) {
      throw new Error(`404: User ${id} not found`);
    }
    existing.active = false;
    existing.meta.lastModified = new Date().toISOString();
    this.users.set(id, existing);
  }

  public getGroups(): SCIMListResponse<SCIMGroupResource> {
    const all = Array.from(this.groups.values());
    return {
      schemas: ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
      totalResults: all.length,
      itemsPerPage: all.length,
      startIndex: 1,
      Resources: all,
    };
  }

  public createGroup(payload: any): SCIMGroupResource {
    const id = payload.id || `scim-grp-${Math.random().toString(36).substring(2, 10)}`;
    const now = new Date().toISOString();

    const resource: SCIMGroupResource = {
      schemas: ["urn:ietf:params:scim:schemas:core:2.0:Group"],
      id,
      displayName: payload.displayName,
      members: payload.members || [],
      meta: {
        resourceType: "Group",
        created: now,
        lastModified: now,
        location: `/scim/v2/Groups/${id}`,
      },
    };

    this.groups.set(id, resource);
    return resource;
  }
}
