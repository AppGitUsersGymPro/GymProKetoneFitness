import { useEffect, useState } from "react";
import api from "../../api/axios";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend
} from "recharts";
import "./Dashboard.css";

const PIE_COLORS  = ["#f97316", "#ef4444", "#94a3b8"];
const CHART_GRID  = "rgba(0,0,0,0.06)";
const TICK_COLOR  = "#94a3b8";

function StatCard({ icon, label, value, sub, color }) {
  return (
    <div className="stat-card animate-in">
      <div className="icon" style={{ background: color + "18", color }}>{icon}</div>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function fmt(n) { return Number(n).toLocaleString("en-IN"); }

export default function Dashboard() {
  const [memberStats, setMemberStats] = useState(null);
  const [staffStats,  setStaffStats]  = useState(null);
  const [eqStats,     setEqStats]     = useState(null);
  const [finance,     setFinance]     = useState(null);
  const [expiring,    setExpiring]    = useState([]);
  const [checkins,    setCheckins]    = useState([]);
  const [loading,     setLoading]     = useState(true);

  useEffect(() => {
    document.getElementById("page-title").textContent = "Dashboard";
    Promise.all([
      api.get("/members/list/stats/"),
      api.get("/staff/members/stats/"),
      api.get("/equipment/list/stats/"),
      api.get("/finances/summary/"),
      api.get("/members/list/expiring_soon/?days=7"),
      api.get("/members/list/today_checkins/"),
    ]).then(([m, s, e, f, ex, ci]) => {
      setMemberStats(m.data);
      setStaffStats(s.data);
      setEqStats(e.data);
      setFinance(f.data);
      setExpiring(ex.data);
      setCheckins(ci.data);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="dash-loading">Loading dashboard…</div>;

  const customTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip__label">{label}</div>
        {payload.map(p => (
          <div key={p.name} style={{ color: p.color, fontWeight: 600, fontSize: 12, fontFamily: "var(--font-body)" }}>
            {p.name}: <span style={{ fontFamily: "var(--font-mono)" }}>₹{fmt(p.value)}</span>
          </div>
        ))}
      </div>
    );
  };

  const todayCheckins = memberStats?.today_checkins ?? 0;
  const todayAbsent   = memberStats?.today_absent   ?? 0;
  const staffPresent  = staffStats?.today_checkins  ?? 0;

  return (
    <div className="dashboard">

      {/* ── Top stats row ── */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <StatCard icon="◈" label="Total Members"   value={memberStats?.total  ?? 0} sub={`${memberStats?.new_this_month ?? 0} new this month`} color="#f97316" />
        <StatCard icon="✓" label="Active Members"  value={memberStats?.active ?? 0} sub={`${memberStats?.expiring_7 ?? 0} expiring in 7 days`} color="#10b981" />
        <StatCard icon="◉" label="Staff Active"    value={staffStats?.active  ?? 0} sub={`${staffStats?.on_leave ?? 0} on leave`}             color="#3b82f6" />
        <StatCard icon="◆" label="Equipment Items" value={eqStats?.total      ?? 0} sub={`${eqStats?.due_maintenance ?? 0} need service`}      color="#8b5cf6" />
      </div>

      {/* ── Finance stats ── */}
      <div className="grid-3" style={{ marginBottom: 24 }}>
        <StatCard icon="₹" label="Monthly Income"  value={`₹${fmt(finance?.total_income  ?? 0)}`} color="#f97316" />
        <StatCard icon="↑" label="Monthly Expense" value={`₹${fmt(finance?.total_expense ?? 0)}`} color="#ef4444" />
        <StatCard icon="★" label="Net Savings"     value={`₹${fmt(finance?.net_savings   ?? 0)}`} color="#10b981" />
      </div>

      {/* ── Today's Check-in stats ── */}
      <div className="checkin-row">
        <StatCard icon="✓" label="Checked In Today"  value={todayCheckins} sub="members present" color="#f97316" />
        <StatCard icon="✗" label="Absent Members"    value={todayAbsent}   sub="active, not yet checked in" color="#ef4444" />
        <StatCard icon="◉" label="Staff Present"     value={staffPresent}  sub="checked in today" color="#3b82f6" />
      </div>

      {/* ── Charts row ── */}
      <div className="dash-charts">
        {/* Income vs Expense trend */}
        <div className="card dash-chart-card">
          <div className="dash-chart-title">Income vs Expense (12 months)</div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={finance?.monthly_trend ?? []} barGap={4} barSize={10}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
              <XAxis dataKey="month" tick={{ fill: TICK_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: TICK_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `₹${v / 1000}k`} />
              <Tooltip content={customTooltip} />
              <Bar dataKey="income"  fill="#f97316" name="Income"  radius={[4,4,0,0]} />
              <Bar dataKey="expense" fill="#ef4444" name="Expense" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Members status pie */}
        <div className="card dash-chart-card">
          <div className="dash-chart-title">Member Status</div>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={[
                  { name: "Active",    value: memberStats?.active    ?? 0 },
                  { name: "Expired",   value: memberStats?.expired   ?? 0 },
                  { name: "Cancelled", value: memberStats?.cancelled ?? 0 },
                ]}
                cx="50%" cy="50%" innerRadius={60} outerRadius={90}
                paddingAngle={3} dataKey="value"
              >
                {PIE_COLORS.map((c, i) => <Cell key={i} fill={c} />)}
              </Pie>
              <Tooltip formatter={(v, n) => [v, n]} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: "12px", color: "#475569" }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Savings trend line */}
        <div className="card dash-chart-card">
          <div className="dash-chart-title">Savings Trend</div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={finance?.monthly_trend ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
              <XAxis dataKey="month" tick={{ fill: TICK_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: TICK_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `₹${v / 1000}k`} />
              <Tooltip content={customTooltip} />
              <Line dataKey="savings" stroke="#10b981" strokeWidth={2.5} dot={false} name="Savings" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Today's Check-ins table ── */}
      <div className="card checkin-table-wrap">
        <div className="dash-table-header">
          <span className="dash-chart-title">Today's Check-ins</span>
          <span className="badge badge-orange">{checkins.length} checked in</span>
        </div>
        {checkins.length === 0 ? (
          <div style={{ textAlign: "center", padding: "32px 16px", color: "var(--text3)", fontSize: 14 }}>
            No members have checked in yet today
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr>
                <th>Member</th>
                <th>Phone</th>
                <th>Check-in</th>
                <th>Check-out</th>
              </tr></thead>
              <tbody>
                {checkins.map(c => (
                  <tr key={c.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div className="checkin-member-avatar">
                          {c.photo
                            ? <img src={c.photo} alt={c.name} />
                            : c.name?.[0]?.toUpperCase()}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600 }}>{c.name}</div>
                          <div style={{ fontSize: 11, color: "var(--text3)", fontFamily: "var(--font-mono)" }}>{c.member_id}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ color: "var(--text3)", fontSize: 12 }}>{c.phone}</td>
                    <td>
                      <span className="badge badge-green">{c.check_in || "—"}</span>
                    </td>
                    <td>
                      {c.check_out
                        ? <span className="badge badge-gray">{c.check_out}</span>
                        : <span className="badge badge-orange">In gym</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Expiring soon table ── */}
      {expiring.length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="dash-table-header">
            <span className="dash-chart-title">⚠ Memberships Expiring in 7 Days</span>
            <span className="badge badge-yellow">{expiring.length} members</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr>
                <th>Member</th><th>Phone</th><th>Plan</th><th>Expires</th><th>Days Left</th>
              </tr></thead>
              <tbody>
                {expiring.map(m => (
                  <tr key={m.id}>
                    <td><b>{m.name}</b></td>
                    <td style={{ color: "var(--text3)" }}>{m.phone}</td>
                    <td>{m.plan_name || "—"}</td>
                    <td style={{ color: "var(--warn)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{m.renewal_date}</td>
                    <td>
                      <span className={`badge ${m.days_until_expiry <= 2 ? "badge-red" : "badge-yellow"}`}>
                        {m.days_until_expiry}d
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
