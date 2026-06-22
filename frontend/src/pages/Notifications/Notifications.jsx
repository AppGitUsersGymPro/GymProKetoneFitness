import { useState, useEffect, useCallback } from "react";
import api from "../../api/axios";
import toast from "react-hot-toast";
import "./Notifications.css";

export default function Notifications() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [phoneFilter, setPhoneFilter] = useState("");
  const [triggerFilter, setTriggerFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");

  useEffect(() => { document.getElementById("page-title").textContent = "Notifications"; }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { ordering: "-created_at", page };
      if (phoneFilter) params.phone = phoneFilter;
      if (triggerFilter) params.trigger_type = triggerFilter;
      if (dateFilter) params.date = dateFilter;
      const res = await api.get("/notifications/", { params });
      setList(res.data.results || res.data);
      setCount(res.data.count || 0);
    } finally { setLoading(false); }
  }, [page, phoneFilter, triggerFilter, dateFilter]);

  useEffect(() => { load(); }, [load]);

  const sendReminders = async () => {
    setSending(true);
    try {
      const res = await api.post("/notifications/send_renewal_reminders/", {});
      toast.success(res.data.message);
      load();
    } catch { toast.error("Failed to send reminders"); } finally { setSending(false); }
  };

  const sendExpiry = async () => {
    setSending(true);
    try {
      const res = await api.post("/notifications/send_expiry_notices/");
      toast.success(`Expiry notices sent to ${res.data.processed} members`);
      load();
    } catch { toast.error("Failed"); } finally { setSending(false); }
  };

  const statusColor  = { sent: "badge-green", failed: "badge-red",  pending: "badge-yellow" };
  const channelColor = { email: "badge-blue", whatsapp: "badge-green", sms: "badge-teal", in_app: "badge-gray" };

  const fmtTrigger = (t) => t.replaceAll("_", " ");

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Notifications</div>
          <div className="page-subtitle">Automated alerts via WhatsApp, Email and SMS</div>
        </div>
      </div>

      {/* Log */}
      <div className="card">

        {/* ── Header: title + filters ── */}
        <div className="notif-log-header">
          <span className="notif-log-title">Notification Log</span>

          <div className="notif-filters">
            <input
              type="tel"
              className="form-input notif-filter-phone"
              placeholder="Filter by phone"
              value={phoneFilter}
              onChange={e => { setPhoneFilter(e.target.value); setPage(1); }}
            />
            <select
              className="form-input notif-filter-trigger"
              value={triggerFilter}
              onChange={e => { setTriggerFilter(e.target.value); setPage(1); }}
            >
              <option value="">All triggers</option>
              <option value="enrollment">New Enrollment</option>
              <option value="renewal_confirm">Renewal Confirmed</option>
              <option value="balance">Balance Payment</option>
              <option value="renewal_remind">Renewal Reminder</option>
              <option value="expiry">Membership Expired</option>
              <option value="pt_renewal">PT Renewal</option>
              <option value="pt_balance">PT Balance Payment</option>
              <option value="absent">Member Absent</option>
              <option value="staff_absent">Staff Absent</option>
              <option value="diet_reminder">Diet Reminder</option>
              <option value="pending_payment_member">Pending Payment (Member)</option>
              <option value="pending_payment_admin">Pending Payment (Admin)</option>
              <option value="new_plan">New Plan Announcement</option>
              <option value="enquiry_welcome">Enquiry Welcome</option>
              <option value="enquiry_followup">Enquiry Follow-up</option>
              <option value="manual">Manual</option>
            </select>
            <input
              type="date"
              className="form-input notif-filter-date"
              value={dateFilter}
              onChange={e => { setDateFilter(e.target.value); setPage(1); }}
            />
            {(phoneFilter || triggerFilter || dateFilter) && (
              <button
                className="btn btn-sm btn-secondary"
                onClick={() => { setPhoneFilter(""); setTriggerFilter(""); setDateFilter(""); setPage(1); }}
              >
                Clear
              </button>
            )}
            <button className="btn btn-sm btn-secondary" onClick={load}>Refresh</button>
          </div>
        </div>

        {/* ── Mobile cards (≤640px) ── */}
        <div className="mobile-card-list" style={{ padding: 12 }}>
          {loading ? (
            <div className="mobile-card__empty">Loading…</div>
          ) : list.length === 0 ? (
            <div className="mobile-card__empty">No notifications yet</div>
          ) : list.map(n => (
            <div key={n.id} className="mobile-card">
              <div className="mobile-card__left">
                <span className="mobile-card__title">{n.recipient_name}</span>
                <span className="mobile-card__meta">{n.recipient_phone}</span>
                <span style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 2 }}>
                  <span className={`badge ${channelColor[n.channel] || "badge-gray"}`} style={{ fontSize: 11 }}>
                    {n.channel}
                  </span>
                  <span className={`badge ${statusColor[n.status] || "badge-gray"}`} style={{ fontSize: 11 }}>
                    {n.status}
                  </span>
                  <span className="mobile-card__meta">{fmtTrigger(n.trigger_type)}</span>
                </span>
                {n.sent_at && (
                  <span className="mobile-card__meta">
                    {new Date(n.sent_at).toLocaleString("en-IN")}
                  </span>
                )}
                {/* Full message — wraps naturally */}
                <span className="notif-mobile-msg">{n.message}</span>
              </div>
            </div>
          ))}
        </div>

        {/* ── Desktop table (>640px) ── */}
        <div className="table-wrap desktop-table-view">
          <table>
            <thead>
              <tr>
                <th>Recipient</th>
                <th>Trigger</th>
                <th>Channel</th>
                <th>Status</th>
                <th>Sent At</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ textAlign: "center", padding: 32 }}>Loading…</td></tr>
              ) : list.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: "center", padding: 32 }}>No notifications yet</td></tr>
              ) : list.map(n => (
                <tr key={n.id}>
                  <td>
                    <div>{n.recipient_name}</div>
                    <div>{n.recipient_phone}</div>
                  </td>
                  <td>{fmtTrigger(n.trigger_type)}</td>
                  <td><span className={`badge ${channelColor[n.channel] || "badge-gray"}`}>{n.channel}</span></td>
                  <td><span className={`badge ${statusColor[n.status] || "badge-gray"}`}>{n.status}</span></td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {n.sent_at ? new Date(n.sent_at).toLocaleString("en-IN") : "—"}
                  </td>
                  {/* Full message — wraps, no truncation */}
                  <td className="notif-msg-cell">{n.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ── Pagination ── */}
        <div className="members-pagination" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 18px", borderTop: "1px solid var(--border)" }}>
          <span style={{ fontSize: 12 }}>{count} total</span>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn btn-sm btn-secondary" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <button className="btn btn-sm btn-secondary" disabled={list.length < 20} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        </div>
      </div>
    </div>
  );
}
