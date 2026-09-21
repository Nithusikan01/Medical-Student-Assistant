import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { deleteUser, listUsers, updateUserRole } from "../api/users";
import { useAuth } from "../auth/useAuth";
import { formatDate } from "../components/admin/Primitives";
import { ArrowLeft, Trash, Users } from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";
import type { AdminUserSummary } from "../types";

/**
 * Who can sign in, and what they may do.
 *
 * Split out of the library page: managing documents and managing people
 * are different jobs with different blast radii, and a mis-click on one
 * page should not be able to delete an account on the other.
 */
export function AdminUsersPage() {
  const { user: currentUser } = useAuth();

  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [usersError, setUsersError] = useState<string | null>(null);

  useEffect(() => {
    listUsers()
      .then(setUsers)
      .catch((caught) => {
        setUsersError(
          caught instanceof Error ? caught.message : "Could not load users.",
        );
      });
  }, []);

  const removeUser = async (target: AdminUserSummary) => {
    setUsersError(null);

    // Deleting an admin needs a stronger confirmation than a plain OK/Cancel
    // - typing the email back proves intent rather than a reflex click.
    if (target.role === "admin") {
      const typed = window.prompt(
        `This permanently deletes the admin account "${target.email}", ` +
          `including their conversations. This cannot be undone.\n\n` +
          `Type their email to confirm.`,
      );

      if (typed === null) {
        return;
      }

      if (typed.trim().toLowerCase() !== target.email.toLowerCase()) {
        setUsersError("Email did not match - nothing was deleted.");
        return;
      }
    } else if (
      !window.confirm(
        `Delete ${target.email}? Their conversations go with them. This cannot be undone.`,
      )
    ) {
      return;
    }

    try {
      await deleteUser(target.id, { confirm: target.role === "admin" });
      setUsers((previous) => previous.filter((row) => row.id !== target.id));
    } catch (caught) {
      setUsersError(
        caught instanceof Error ? caught.message : "Could not delete user.",
      );
    }
  };

  const toggleRole = async (target: AdminUserSummary) => {
    setUsersError(null);
    const nextRole = target.role === "admin" ? "user" : "admin";

    const confirmed = window.confirm(
      nextRole === "admin"
        ? `Make ${target.email} an admin? They will be able to manage the ` +
            `document library and every user, including deleting them.`
        : `Remove admin access from ${target.email}?`,
    );

    if (!confirmed) {
      return;
    }

    try {
      const updated = await updateUserRole(target.id, nextRole);
      setUsers((previous) =>
        previous.map((row) => (row.id === updated.id ? updated : row)),
      );
    } catch (caught) {
      setUsersError(
        caught instanceof Error ? caught.message : "Could not update role.",
      );
    }
  };

  return (
    <div className="admin-shell">
      <div className="admin-bar">
        <Link to="/" className="back-link">
          <ArrowLeft />
          Back to chat
        </Link>
        <ThemeToggle compact />
      </div>

      <div className="admin-body">
        <div className="admin-inner">
          <div>
            <h1>Users</h1>
            <p className="tagline">
              Everyone who has registered, newest first.
            </p>
            <p className="mon-links">
              <Link to="/admin/monitoring">&larr; Admin dashboard</Link>
            </p>
          </div>

          <div className="admin-section">

            {usersError && (
              <p className="upload-status upload-error">{usersError}</p>
            )}

            {users.length === 0 ? (
              !usersError && (
                <div className="empty-state">
                  <span className="empty-state-icon">
                    <Users size={24} strokeWidth={1.5} />
                  </span>
                  <div>
                    <strong>No one has joined yet</strong>
                    <p>Registered users will show up here.</p>
                  </div>
                </div>
              )
            ) : (
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Joined</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => {
                      const isSelf = user.id === currentUser?.id;

                      return (
                        <tr key={user.id}>
                          <td>
                            <span className="file-cell">
                              <Users />
                              {user.full_name ?? user.email}
                            </span>
                            {user.full_name && (
                              <span className="cell-sub">{user.email}</span>
                            )}
                          </td>
                          <td>
                            <span
                              className={`badge ${
                                user.role === "admin"
                                  ? "badge-processing"
                                  : "badge-ready"
                              }`}
                            >
                              <span className="badge-dot" />
                              {user.role}
                            </span>
                          </td>
                          <td className="dim">
                            {user.is_active ? "Active" : "Inactive"}
                          </td>
                          <td className="dim">{formatDate(user.created_at)}</td>
                          <td>
                            <span className="row-actions">
                              <button
                                type="button"
                                className="btn btn-secondary btn-small"
                                onClick={() => void toggleRole(user)}
                              >
                                {user.role === "admin"
                                  ? "Remove admin"
                                  : "Make admin"}
                              </button>

                              <button
                                type="button"
                                className="btn btn-danger btn-small"
                                disabled={isSelf}
                                title={
                                  isSelf
                                    ? "You cannot delete your own account."
                                    : undefined
                                }
                                onClick={() => void removeUser(user)}
                              >
                                <Trash size={13} />
                                Delete
                              </button>
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
