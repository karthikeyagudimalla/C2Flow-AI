
import { registerUser, loginUser, apiRequest } from "./api";


import { useEffect, useState } from "react";

import {

  LayoutDashboard,

  ListTodo,

  Workflow,

  Settings,

  Sparkles,

  Plus,

  Sun,

  Moon,

  CheckCircle2,

  Clock,

  Bell,

  CalendarClock,

  ShieldCheck,

  ArrowUpRight,

  Trash2,

  LogOut,

} from "lucide-react";

import "./index.css";



const taskStatusFromApi = {
  pending: "To Do",
  in_progress: "In Progress",
  completed: "Done",
  cancelled: "Cancelled",
};

const taskStatusToApi = {
  "To Do": "pending",
  "In Progress": "in_progress",
  Done: "completed",
  Cancelled: "cancelled",
};

function taskFromApi(task) {
  return {
    ...task,
    status: taskStatusFromApi[task.status] || "To Do",
    priority: task.priority
      ? task.priority[0].toUpperCase() + task.priority.slice(1)
      : "Medium",
  };
}



const navigation = [

  { name: "Dashboard", icon: LayoutDashboard },

  { name: "Task Manager", icon: ListTodo },

  { name: "AI Flow", icon: Sparkles },

  { name: "Task Board", icon: Workflow },

  { name: "Workflows", icon: Workflow },

  { name: "Reminders", icon: Bell },

  { name: "Approvals", icon: ShieldCheck },

  { name: "Settings", icon: Settings },

];



export default function App() {

  const [signedIn, setSignedIn] = useState(false);

  const [legalPage, setLegalPage] = useState("");

  const [email, setEmail] = useState("");

  const [password, setPassword] = useState("");

  const [authMode, setAuthMode] = useState("signup");

  const [authError, setAuthError] = useState("");

  const [token, setToken] = useState("");

  const [authLoading, setAuthLoading] = useState(false);



  const [page, setPage] = useState("Dashboard");

  const [dark, setDark] = useState(() =>
    window.localStorage.getItem("c2flow_theme") !== "light"
  );

  const [tasks, setTasks] = useState([]);
  const [taskError, setTaskError] = useState("");

  const [reminders, setReminders] = useState([]);

  const [workflows, setWorkflows] = useState([]);

  const [approvals, setApprovals] = useState([]);

  const [resourceError, setResourceError] = useState("");

  const [reminderTitle, setReminderTitle] = useState("");

  const [reminderAt, setReminderAt] = useState("");

  const [reminderDrafts, setReminderDrafts] = useState({});

  const [workflowName, setWorkflowName] = useState("");

  const [workflowDescription, setWorkflowDescription] = useState("");

  const [assistantReply, setAssistantReply] = useState(null);

  const [approvalPreview, setApprovalPreview] = useState(null);

  const [newTitle, setNewTitle] = useState("");

  const [newDescription, setNewDescription] = useState("");

  const [prompt, setPrompt] = useState("");


  async function loadWorkspace(accessToken) {
    const [user, backendTasks, backendReminders, backendWorkflows, backendApprovals] =
      await Promise.all([
        apiRequest("/api/auth/me", { token: accessToken }),
        apiRequest("/api/tasks", { token: accessToken }),
        apiRequest("/api/reminders", { token: accessToken }),
        apiRequest("/api/workflows", { token: accessToken }),
        apiRequest("/api/approvals", { token: accessToken }),
      ]);

    setEmail(user.email);
    setTasks(backendTasks.map(taskFromApi));
    setReminders(backendReminders);
    setWorkflows(backendWorkflows);
    setApprovals(backendApprovals);
  }

  useEffect(() => {
    const savedToken = window.localStorage.getItem("c2flow_access_token");
    if (!savedToken) return;

    // Session restoration must hydrate the workspace after the initial render.
    // oxlint-disable-next-line react/set-state-in-effect
    loadWorkspace(savedToken)
      .then(() => {
        setToken(savedToken);
        setSignedIn(true);
      })
      .catch(() => {
        window.localStorage.removeItem("c2flow_access_token");
        setToken("");
      });
  }, []);

  useEffect(() => {
    window.localStorage.setItem("c2flow_theme", dark ? "dark" : "light");
  }, [dark]);



  const completed = tasks.filter(

    (task) => task.status === "Done"

  ).length;



  const pending = tasks.filter(
    (task) => task.status !== "Done" && task.status !== "Cancelled"
  ).length;



  async function addTask(event) {
    event.preventDefault();
    const title = newTitle.trim();
    if (!title) return;

    setTaskError("");
    try {
      const created = await apiRequest("/api/tasks", {
        token,
        method: "POST",
        body: JSON.stringify({
          title,
          description: newDescription.trim() || null,
          priority: "medium",
        }),
      });
      setTasks((old) => [taskFromApi(created), ...old]);
      setNewTitle("");
      setNewDescription("");
    } catch (error) {
      setTaskError(error.message || "Could not save this task.");
    }
  }

  async function updateTask(taskId, changes) {
    setTaskError("");
    try {
      const updated = await apiRequest(`/api/tasks/${taskId}`, {
        token,
        method: "PATCH",
        body: JSON.stringify({
          ...changes,
          ...(changes.status ? { status: taskStatusToApi[changes.status] } : {}),
          ...(changes.priority ? { priority: changes.priority.toLowerCase() } : {}),
        }),
      });
      setTasks((old) => old.map((task) =>
        task.id === taskId ? taskFromApi(updated) : task
      ));
    } catch (error) {
      setTaskError(error.message || "Could not update this task.");
    }
  }

  async function deleteTask(taskId) {
    setTaskError("");
    try {
      await apiRequest(`/api/tasks/${taskId}`, { token, method: "DELETE" });
      setTasks((old) => old.filter((task) => task.id !== taskId));
    } catch (error) {
      setTaskError(error.message || "Could not delete this task.");
    }
  }



  async function sendAssistantMessage(event) {
    event.preventDefault();
    if (!prompt.trim()) return;

    const goal = prompt.trim();
    setResourceError("");
    try {
      const reply = await apiRequest("/api/assistant", {
        token,
        method: "POST",
        body: JSON.stringify({ message: goal }),
      });
      setAssistantReply(reply);

      if (["list_tasks", "list_pending_tasks"].includes(reply.intent)) {
        setTasks(reply.data.map(taskFromApi));
      } else if (reply.intent === "list_reminders") {
        setReminders(reply.data);
      } else if (reply.intent === "list_workflows") {
        setWorkflows(reply.data);
      } else if (reply.intent === "create_task" && reply.data?.id) {
        setTasks((old) => [taskFromApi(reply.data), ...old]);
      } else if (reply.intent === "create_reminder" && reply.data?.id) {
        setReminders((old) => [...old, reply.data]);
      } else if (reply.intent === "complete_task" && reply.data?.id) {
        setTasks((old) => old.map((task) =>
          task.id === reply.data.id ? taskFromApi({ ...task, ...reply.data }) : task
        ));
      } else if (reply.requires_approval) {
        const currentApprovals = await apiRequest("/api/approvals", { token });
        setApprovals(currentApprovals);
      }
    } catch (error) {
      setResourceError(error.message || "The assistant request failed.");
    }
  }

  async function createReminder(event) {
    event.preventDefault();
    setResourceError("");
    try {
      const created = await apiRequest("/api/reminders", {
        token,
        method: "POST",
        body: JSON.stringify({
          title: reminderTitle.trim(),
          remind_at: new Date(reminderAt).toISOString(),
        }),
      });
      setReminders((old) => [...old, created].sort(
        (a, b) => new Date(a.remind_at) - new Date(b.remind_at)
      ));
      setReminderTitle("");
      setReminderAt("");
    } catch (error) {
      setResourceError(error.message || "Could not save this reminder.");
    }
  }

  async function updateReminder(reminderId, changes) {
    setResourceError("");
    try {
      const updated = await apiRequest(`/api/reminders/${reminderId}`, {
        token,
        method: "PATCH",
        body: JSON.stringify(changes),
      });
      setReminders((old) => old.map((item) =>
        item.id === reminderId ? updated : item
      ));
    } catch (error) {
      setResourceError(error.message || "Could not update this reminder.");
    }
  }

  async function deleteReminder(reminderId) {
    setResourceError("");
    try {
      await apiRequest(`/api/reminders/${reminderId}`, {
        token,
        method: "DELETE",
      });
      setReminders((old) => old.filter((item) => item.id !== reminderId));
    } catch (error) {
      setResourceError(error.message || "Could not delete this reminder.");
    }
  }

  async function createWorkflow(event) {
    event.preventDefault();
    setResourceError("");
    try {
      const created = await apiRequest("/api/workflows", {
        token,
        method: "POST",
        body: JSON.stringify({
          name: workflowName.trim(),
          description: workflowDescription.trim() || null,
        }),
      });
      setWorkflows((old) => [created, ...old]);
      setWorkflowName("");
      setWorkflowDescription("");
    } catch (error) {
      setResourceError(error.message || "Could not save this workflow.");
    }
  }

  async function updateWorkflow(workflowId, changes) {
    setResourceError("");
    try {
      const updated = await apiRequest(`/api/workflows/${workflowId}`, {
        token,
        method: "PATCH",
        body: JSON.stringify(changes),
      });
      setWorkflows((old) => old.map((item) =>
        item.id === workflowId ? updated : item
      ));
    } catch (error) {
      setResourceError(error.message || "Could not update this workflow.");
    }
  }

  async function deleteWorkflow(workflowId) {
    setResourceError("");
    try {
      await apiRequest(`/api/workflows/${workflowId}`, {
        token,
        method: "DELETE",
      });
      setWorkflows((old) => old.filter((item) => item.id !== workflowId));
    } catch (error) {
      setResourceError(error.message || "Could not delete this workflow.");
    }
  }

  async function loadApprovalPreview(approvalId) {
    setResourceError("");
    try {
      const preview = await apiRequest(
        `/api/approvals/${approvalId}/preview`,
        { token },
      );
      setApprovalPreview(preview);
    } catch (error) {
      setResourceError(error.message || "Could not load approval details.");
    }
  }

  async function decideApproval(approvalId, decision) {
    setResourceError("");
    try {
      const updated = await apiRequest(`/api/approvals/${approvalId}`, {
        token,
        method: "PATCH",
        body: JSON.stringify({ decision }),
      });
      setApprovals((old) => old.map((item) =>
        item.id === approvalId ? updated : item
      ));
      if (approvalPreview?.id === approvalId) {
        setApprovalPreview((old) => ({ ...old, status: decision }));
      }
    } catch (error) {
      setResourceError(error.message || "Could not update this approval.");
    }
  }

  function signOut() {
    window.localStorage.removeItem("c2flow_access_token");
    setToken("");
    setSignedIn(false);
    setTasks([]);
    setReminders([]);
    setWorkflows([]);
    setApprovals([]);
    setPassword("");
    setPage("Dashboard");
  }



if (legalPage === "privacy") {

  return (

    <div className="legal-page">

      <div className="legal-card">

        <div className="legal-brand">

          <span className="legal-logo">

            <Workflow size={25} />

          </span>

          <span>

            C2Flow<span>AI</span>

          </span>

        </div>



        <span className="legal-eyebrow">YOUR PRIVACY MATTERS</span>

        <h1>Privacy Policy</h1>

        <p className="legal-intro">

          How C2Flow AI handles information when you use

          our application.

        </p>



        <div className="legal-section">

          <h2>1. Information We Handle</h2>

          <p>

            C2Flow AI is a demonstration application. Your

            account email and workspace tasks are stored by

            the connected backend for your account.

          </p>

        </div>



        <div className="legal-section">

          <h2>2. How Information Is Used</h2>

          <p>

            Account information is used to authenticate you.

            Tasks you create are used to display and manage

            your workspace across sessions.

          </p>

        </div>



        <div className="legal-section">

          <h2>3. Storage and Security</h2>

          <p>

            Account passwords are stored as password hashes.

            Workspace records are associated with your account

            in the configured backend database.

          </p>

        </div>



        <div className="legal-section">

          <h2>4. Third-Party Services</h2>

          <p>

            Google and Apple sign-in are displayed as demo

            buttons. Their authentication services have not

            been integrated in the current version.

          </p>

        </div>



        <div className="legal-section">

          <h2>5. Changes to This Policy</h2>

          <p>

            This policy should be updated as C2Flow AI

            adds real authentication, data storage, analytics,

            or third-party integrations.

          </p>

        </div>



        <div className="legal-notice">

          This is a demonstration policy for the current

          MVP, not a substitute for a reviewed legal policy.

        </div>



        <button

          className="legal-back"

          onClick={() => setLegalPage("")}

        >

          ← Back to sign up

        </button>

      </div>

    </div>

  );

}



  // Show the authentication page before the dashboard.

if (!signedIn) {

  return (

    <div className="auth-page">

      <div className="auth-glow auth-glow-one" />

      <div className="auth-glow auth-glow-two" />



      <div className="auth-shell">

        <div className="auth-top">

          <span className="auth-mini-brand">

            <span className="auth-logo">

              <Workflow size={23} />

            </span>

            C2Flow<span>AI</span>

          </span>

          <span className="auth-secure">

            <span className="auth-live-dot" />

            Workspace access

          </span>

        </div>



        <section className="auth-card">

          <div className="auth-brand-mark">

            <Workflow size={29} />

          </div>



          <div className="auth-heading">

            <span className="auth-eyebrow">

              {authMode === "signin"

                ? "WELCOME BACK"

                : "GET STARTED"}

            </span>



            <h1>

              {authMode === "signin"

                ? "Welcome back."

                : authMode === "password"

                ? "Almost there."

                : "Create your account."}

            </h1>



            <p>

              {authMode === "signin"

                ? "Sign in to continue to your C2Flow AI workspace."

                : authMode === "password"

                ? "Create a password to finish setting up your account."

                : "Your team's next great workflow starts here."}

            </p>

          </div>



          <form

            className="auth-form"

            onSubmit={async (event) => {
              event.preventDefault();
              setAuthError("");

              // First signup step: collect the email before asking for a password.
              if (authMode === "signup") {
                setAuthMode("password");
                return;
              }

              setAuthLoading(true);
              try {
                if (authMode === "password") {
                  await registerUser(email, password);
                }

                
                const result = await loginUser(email, password);
                setToken(result.access_token);
                window.localStorage.setItem(
                  "c2flow_access_token",
                  result.access_token,
                );
                await loadWorkspace(result.access_token);
                setSignedIn(true);
                setPage("Dashboard");
                setPassword("");

              } catch (error) {
                window.localStorage.removeItem("c2flow_access_token");
                setToken("");
                setAuthError(error.message || "Authentication failed. Please try again.");
              } finally {
                setAuthLoading(false);
              }
            }}
          >
            <label htmlFor="auth-email">EMAIL ADDRESS</label>



            <input

              id="auth-email"

              className="auth-input"

              type="email"

              placeholder="you@company.com"

              value={email}

              onChange={(event) => {

                setEmail(event.target.value);

                setAuthError("");

              }}

              autoComplete="email"

              required

            />



            {authMode !== "signup" && (

              <>

                <label htmlFor="auth-password">PASSWORD</label>



                <input

                  id="auth-password"

                  className="auth-input"

                  type="password"

                  placeholder="Enter your password"

                  value={password}

                  onChange={(event) => {

                    setPassword(event.target.value);

                    setAuthError("");

                  }}

                  autoComplete={

                    authMode === "signin"

                      ? "current-password"

                      : "new-password"

                  }

                  minLength={12}

                  required

                />

              </>

            )}



            {authError && (

              <p className="auth-error" role="alert">

                {authError}

              </p>

            )}



            <button className="auth-primary" type="submit" disabled={authLoading}>
              {authLoading
                ? "Please wait..."
                : authMode === "signup"
                ? "Continue with email"
                : authMode === "signin"
                ? "Sign in to C2Flow AI"
                : "Create account"}
              <ArrowUpRight size={18} />
            </button>

          </form>



          <div className="auth-divider">

            <span />

            <p>OR CONTINUE WITH</p>

            <span />

          </div>



          <div className="auth-socials">

            <button

              type="button"

              className="auth-social"

              onClick={() =>

                setAuthError(

                  "Google sign-in requires Google OAuth setup."

                )

              }

            >

              <span className="google-mark">G</span>

              <span>Continue with Google</span>

            </button>



            <button

              type="button"

              className="auth-social"

              onClick={() =>

                setAuthError(

                  "Apple sign-in requires Apple authentication setup."

                )

              }

            >

              <span className="apple-mark">●</span>

              <span>Continue with Apple</span>

            </button>

          </div>



          <div className="auth-switch">

            {authMode === "signin" ? (

              <>

                Don't have an account?{" "}

                <button

                  type="button"

                  onClick={() => {

                    setAuthMode("signup");

                    setPassword("");

                    setAuthError("");

                  }}

                >

                  Create account

                </button>

              </>

            ) : authMode === "password" ? (

              <button

                type="button"

                onClick={() => {

                  setAuthMode("signup");

                  setPassword("");

                  setAuthError("");

                }}

              >

                ← Back to email

              </button>

            ) : (

              <>

                Already have an account?{" "}

                <button

                  type="button"

                  onClick={() => {

                    setAuthMode("signin");

                    setPassword("");

                    setAuthError("");

                  }}

                >

                  Sign in

                </button>

              </>

            )}

          </div>



          <p className="auth-terms">

            By continuing, you agree to our{" "}



<a href="#terms">Terms of Service</a> and{" "}


              <a
                href="#privacy"
                onClick={(event) => {
                  event.preventDefault();
                  setLegalPage("privacy");
                }}
              >
                Privacy Policy
              </a>.


          </p>

        </section>



        <footer className="auth-footer">

          <span>C2Flow AI</span>

          <span>·</span>

          Built for teams that move forward.

        </footer>

      </div>

    </div>

  );

}



  // The main application appears after sign-in.

  return (

    <div className={`app ${dark ? "dark" : "light"}`}>

      <aside className="sidebar">

        <div className="brand">

          <span className="brand-icon">

            <Workflow size={23} />

          </span>

          <span>

            C2Flow<span className="violet"> AI</span>

          </span>

        </div>



        <div className="workspace">

          <div className="workspace-avatar">F</div>

          <div>

            <strong>C2Flow Studio</strong>

            <small>Hackathon workspace</small>

          </div>

        </div>



        <p className="nav-heading">WORKSPACE</p>



        <nav>

          {navigation.map(({ name, icon: Icon }) => (

            <button

              key={name}

              onClick={() => setPage(name)}

              className={`nav-item ${

                page === name ? "active" : ""

              }`}

            >

              <Icon size={18} />

              <span>{name}</span>



              {name === "AI Flow" && (

                <span className="ai-label">AI</span>

              )}

            </button>

          ))}

        </nav>



        <div className="sidebar-bottom">

          <div className="tip">

            <Sparkles size={20} />

            <strong>Work smarter.</strong>

            <p>Turn your ideas into actionable plans.</p>

            <button onClick={() => setPage("AI Flow")}>

              Try AI Flow →

            </button>

          </div>



          <div className="user-profile">

            <div className="user-avatar">

              {email ? email.slice(0, 2).toUpperCase() : "YO"}

            </div>

            <div>

              <strong>{email || "Your workspace"}</strong>

              <small>Workspace member</small>

            </div>

            <button

              className="delete-btn"

              title="Sign out"

              aria-label="Sign out"
              onClick={signOut}

            >

              <LogOut size={16} />

            </button>

          </div>

        </div>

      </aside>



      <main className="main">

        <header className="topbar">

          <div className="breadcrumb">

            Workspace <span>/</span> <strong>{page}</strong>

          </div>



          <button

            className="theme-toggle"

            onClick={() => setDark(!dark)}

            aria-label="Toggle color theme"

          >

            {dark ? <Sun size={18} /> : <Moon size={18} />}

            {dark ? "Light mode" : "Dark mode"}

          </button>

        </header>



        <div className="content" key={page}>

          <div className="page-header">

            <div>

              <div className="eyebrow">

                <span className="live-dot" />

                YOUR COMMAND CENTER

              </div>



              <h1>{page}</h1>



              <p>

                {{

                  Dashboard: "Your work, organized in one place.",

                  "Task Manager":

                    "Create tasks and keep your work moving.",

                  "AI Flow":

                    "Turn an idea into an actionable plan.",

                  "Task Board": "Move tasks through your work stages.",

                  Workflows:

                    "Create and manage saved workflows.",

                  Reminders: "Keep track of scheduled follow-ups.",

                  Approvals: "Review pending assistant actions.",

                  Settings:

                    "Personalize your C2Flow AI experience.",

                }[page]}

              </p>

            </div>



            {(page === "Dashboard" ||

              page === "Task Manager") && (

              <button

                className="primary-btn"

                onClick={() => setPage("Task Manager")}

              >

                <Plus size={17} />

                Manage tasks

              </button>

            )}

          </div>



          {taskError && <p className="auth-error" role="alert">{taskError}</p>}

          {resourceError && <p className="auth-error" role="alert">{resourceError}</p>}

          {page === "Dashboard" && (

            <>

              <section className="hero">

                <div className="hero-copy">

                  <span className="hero-label">

                    <Sparkles size={14} />

                    YOUR AI OPERATIONS AGENT

                  </span>



                  <h2>

                    Less busywork.

                    <br />

                    <span>More meaningful work.</span>

                  </h2>



                  <p>

                    Organize tasks, streamline workflows, and

                    help your team focus on what matters.

                  </p>



                  <button

                    className="hero-btn"

                    onClick={() => setPage("AI Flow")}

                  >

                    Build a workflow

                    <ArrowUpRight size={17} />

                  </button>

                </div>



                <div className="hero-art">

                  <div className="orbit orbit-one" />

                  <div className="orbit orbit-two" />

                  <div className="hero-cube">

                    <Workflow size={47} />

                  </div>

                  <span className="floating-tag">

                    ✦ AI powered

                  </span>

                </div>

              </section>



              <section className="stats">

                <Stat

                  icon={<ListTodo />}

                  label="Total tasks"

                  value={tasks.length}

                  color="purple"

                />

                <Stat

                  icon={<CheckCircle2 />}

                  label="Completed"

                  value={completed}

                  color="green"

                />

                <Stat

                  icon={<Clock />}

                  label="Pending"

                  value={pending}

                  color="blue"

                />

                <Stat

                  icon={<Workflow />}

                  label="Workflows"

                  value={workflows.length}

                  color="orange"

                />

              </section>



              <section className="panel">

                <div className="panel-header">

                  <div>

                    <h3>Recent tasks</h3>

                    <p>Your latest work items</p>

                  </div>



                  <button

                    className="link-btn"

                    onClick={() => setPage("Task Manager")}

                  >

                    View all →

                  </button>

                </div>



                <TaskList

                  tasks={tasks.slice(0, 5)}

                  updateTask={updateTask}
                  deleteTask={deleteTask}

                />

              </section>

            </>

          )}



          {page === "Task Manager" && (

            <section className="panel">

              <div className="panel-header">

                <div>

                  <h3>Manage your tasks</h3>

                  <p>Add, complete, or delete work items.</p>

                </div>

              </div>



              <form className="add-form" onSubmit={addTask}>

                <input

                  value={newTitle}

                  onChange={(event) =>

                    setNewTitle(event.target.value)

                  }

                  placeholder="Enter a new task..."

                  aria-label="New task title"

                />

                <input
                  value={newDescription}
                  onChange={(event) => setNewDescription(event.target.value)}
                  placeholder="Description (optional)"
                  aria-label="New task description"
                />



                <button className="primary-btn" type="submit">

                  <Plus size={16} />

                  Add task

                </button>

              </form>



              <TaskList tasks={tasks} updateTask={updateTask} deleteTask={deleteTask} />

            </section>

          )}



          {page === "AI Flow" && (

            <section className="ai-layout">

              <div className="panel ai-panel">

                <div className="ai-icon">

                  <Sparkles size={25} />

                </div>



                <h2>Workspace assistant</h2>

                <p>

                  Run a supported command for tasks, reminders, workflows, or approvals.

                </p>



                <form onSubmit={sendAssistantMessage}>

                    <label htmlFor="goal">COMMAND</label>



                  <textarea

                    id="goal"

                    rows={5}

                    value={prompt}

                    onChange={(event) => {
                      setPrompt(event.target.value);
                      setAssistantReply(null);
                    }}

                    placeholder="Examples: create task: Prepare demo · show my reminders"

                    required

                  />



                  <button

                    className="primary-btn generate-btn"

                    type="submit"

                  >

                    <Sparkles size={17} />

                    Run command

                  </button>

                </form>

                <p className="hint">

                  Try “create task: Prepare demo”, “show my tasks”, “create reminder: Review demo at 2026-10-12T11:00+05:30”, or “send email”.

                </p>

              </div>



              <div className="panel">

                <div className="panel-header">

                  <div>

                    <h3>Assistant response</h3>

                    <p>Your assistant response appears here.</p>

                  </div>

                </div>



                {assistantReply ? (

                  <div className="success-message">

                    <CheckCircle2 size={20} />

                    {assistantReply.message}

                    {assistantReply.data?.id && <button

                      className="link-btn"

                      onClick={() => setPage("Task Manager")}

                    >

                      View tasks →

                    </button>}

                  </div>

                ) : (

                  <div className="empty">

                    <Workflow size={38} />

                    <h3>Your next idea starts here</h3>

                    <p>

                      Enter a request to create a task in your workspace.

                    </p>

                  </div>

                )}

              </div>

            </section>

          )}



          {page === "Task Board" && (

            <section className="kanban">

              {["To Do", "In Progress", "Done", "Cancelled"].map((status) => (

                <div className="kanban-column" key={status}>

                  <h3>

                    {status}

                    <span>

                      {

                        tasks.filter(

                          (task) => task.status === status

                        ).length

                      }

                    </span>

                  </h3>



                  {tasks

                    .filter((task) => task.status === status)

                    .map((task) => (

                      <div className="kanban-card" key={task.id}>

                        <span

                          className={`priority ${task.priority.toLowerCase()}`}

                        >

                          {task.priority}

                        </span>



                        <h4>{task.title}</h4>



                        <select

                          aria-label={`Status for ${task.title}`}

                          value={task.status}

                          onChange={(event) =>
                            updateTask(task.id, { status: event.target.value })
                          }

                        >

                          <option>To Do</option>

                          <option>In Progress</option>

                          <option>Done</option>

                          <option>Cancelled</option>

                        </select>

                      </div>

                    ))}

                </div>

              ))}

            </section>

          )}



          {page === "Workflows" && (
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3>Saved workflows</h3>
                  <p>Workflows are stored with your account.</p>
                </div>
              </div>

              <form className="add-form" onSubmit={createWorkflow}>
                <input
                  value={workflowName}
                  onChange={(event) => setWorkflowName(event.target.value)}
                  placeholder="Workflow name"
                  aria-label="Workflow name"
                  required
                />
                <input
                  value={workflowDescription}
                  onChange={(event) => setWorkflowDescription(event.target.value)}
                  placeholder="Description (optional)"
                  aria-label="Workflow description"
                />
                <button className="primary-btn" type="submit">
                  <Plus size={16} /> Create workflow
                </button>
              </form>

              {!workflows.length ? (
                <div className="empty"><Workflow size={30} /><h3>No workflows yet</h3><p>Create a workflow to track a repeatable process.</p></div>
              ) : (
                <div className="task-list">
                  {workflows.map((workflow) => (
                    <div className="task-row" key={workflow.id}>
                      <div className="task-title">
                        <strong>{workflow.name}</strong>
                        <small>{workflow.description || "No description"}</small>
                      </div>
                      <select
                        aria-label={`Status for ${workflow.name}`}
                        value={workflow.status}
                        onChange={(event) => updateWorkflow(workflow.id, { status: event.target.value })}
                      >
                        <option value="draft">Draft</option>
                        <option value="active">Active</option>
                        <option value="paused">Paused</option>
                        <option value="completed">Completed</option>
                      </select>
                      <button className="delete-btn" aria-label={`Delete ${workflow.name}`} onClick={() => deleteWorkflow(workflow.id)}>
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {page === "Reminders" && (
            <section className="panel">
              <div className="panel-header">
                <div><h3>Scheduled reminders</h3><p>Reminders are saved to your account with their timezone.</p></div>
              </div>
              <form className="add-form" onSubmit={createReminder}>
                <input
                  value={reminderTitle}
                  onChange={(event) => setReminderTitle(event.target.value)}
                  placeholder="What should we remind you about?"
                  aria-label="Reminder title"
                  required
                />
                <input
                  type="datetime-local"
                  value={reminderAt}
                  onChange={(event) => setReminderAt(event.target.value)}
                  aria-label="Reminder date and time"
                  required
                />
                <button className="primary-btn" type="submit"><CalendarClock size={16} /> Add reminder</button>
              </form>
              {!reminders.length ? (
                <div className="empty"><Bell size={30} /><h3>No reminders yet</h3><p>Add a date and time for your next follow-up.</p></div>
              ) : (
                <div className="task-list">
                  {reminders.map((reminder) => (
                    <div className="task-row" key={reminder.id}>
                      <div className="task-title">
                        <strong>{reminderDrafts[reminder.id] ?? reminder.title}</strong>
                        <small>{new Date(reminder.remind_at).toLocaleString()}</small>
                      </div>
                      <form className="add-form" onSubmit={(event) => {
                        event.preventDefault();
                        updateReminder(reminder.id, {
                          title: reminderDrafts[reminder.id] ?? reminder.title,
                        });
                      }}>
                        <input
                          value={reminderDrafts[reminder.id] ?? reminder.title}
                          onChange={(event) => setReminderDrafts((old) => ({
                            ...old,
                            [reminder.id]: event.target.value,
                          }))}
                          aria-label={`Edit ${reminder.title}`}
                        />
                        <button className="secondary-btn" type="submit">Save</button>
                      </form>
                      <span className="task-status">{reminder.status}</span>
                      <button className="delete-btn" aria-label={`Delete ${reminder.title}`} onClick={() => deleteReminder(reminder.id)}><Trash2 size={15} /></button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {page === "Approvals" && (
            <section className="panel">
              <div className="panel-header">
                <div><h3>Action approvals</h3><p>Review proposed email and calendar actions before they are approved.</p></div>
              </div>
              {!approvals.length ? (
                <div className="empty"><ShieldCheck size={30} /><h3>No approvals to review</h3><p>Assistant proposals that need approval will appear here.</p></div>
              ) : (
                <div className="task-list">
                  {approvals.map((approval) => (
                    <div className="task-row" key={approval.id}>
                      <div className="task-title">
                        <strong>{approval.action_type.replaceAll("_", " ")}</strong>
                        <small>{new Date(approval.created_at).toLocaleString()}</small>
                      </div>
                      <span className="task-status">{approval.status}</span>
                      <button className="secondary-btn" onClick={() => loadApprovalPreview(approval.id)}>Review details</button>
                      {approval.status === "pending" && <>
                        <button className="secondary-btn" onClick={() => decideApproval(approval.id, "approved")}>Approve</button>
                        <button className="secondary-btn" onClick={() => decideApproval(approval.id, "rejected")}>Reject</button>
                      </>}
                    </div>
                  ))}
                </div>
              )}
              {approvalPreview && (
                <div className="panel approval-preview">
                  <div className="panel-header"><div><h3>Approval #{approvalPreview.id}</h3><p>{approvalPreview.action_type.replaceAll("_", " ")} · {approvalPreview.status}</p></div></div>
                  <pre>{JSON.stringify(approvalPreview.payload, null, 2)}</pre>
                </div>
              )}
              <p className="hint">Approving records your decision. Sending email and calendar execution require a configured external integration.</p>
            </section>
          )}

          {page === "Settings" && (

            <section className="panel settings-panel">

              <div className="panel-header">

                <div>

                  <h3>Appearance</h3>

                  <p>Choose your preferred display mode.</p>

                </div>

              </div>



              <div className="setting-row">

                <div>

                  <strong>Color theme</strong>

                  <p>Switch between dark and light appearances.</p>

                </div>



                <button

                  className="secondary-btn"

                  onClick={() => setDark(!dark)}

                >

                  {dark ? <Sun size={17} /> : <Moon size={17} />}

                  {dark ? "Switch to light" : "Switch to dark"}

                </button>

              </div>



              <div className="setting-row">

                <div>

                  <strong>Application</strong>

                  <p>C2Flow AI · Connected workspace</p>

                </div>

                  <span className="ai-label">API</span>

              </div>



              <div className="setting-row">

                <div>

                  <strong>Data storage</strong>

                  <p>

                    Tasks, workflows, reminders, and approvals are stored in the backend.

                  </p>

                </div>

              </div>



              <div className="setting-row">

                <div>

                  <strong>Sign out</strong>

                  <p>Return to the login page.</p>

                </div>



                <button

                  className="secondary-btn"

                  onClick={signOut}

                >

                  <LogOut size={16} />

                  Sign out

                </button>

              </div>

            </section>

          )}



          <footer>

            C2Flow AI <span>·</span> Built for teams that move forward.

          </footer>

        </div>

      </main>

    </div>

  );

}



function Stat({ icon, label, value, color }) {

  return (

    <div className="stat-card">

      <div className={`stat-icon ${color}`}>{icon}</div>

      <span>{label}</span>

      <strong>{value}</strong>

      <small>Live workspace count</small>

    </div>

  );

}



function TaskList({ tasks, updateTask, deleteTask }) {

  if (!tasks.length) {

    return (

      <div className="empty">

        <ListTodo size={30} />

        <h3>No tasks yet</h3>

        <p>Create your first task to get started.</p>

      </div>

    );

  }



  return (

    <div className="task-list">

      {tasks.map((task) => (

        <div className="task-row" key={task.id}>

          <button

            className={`task-check ${

              task.status === "Done" ? "checked" : ""

            }`}

            aria-label={`Toggle completion for ${task.title}`}

            onClick={() => updateTask(task.id, {
              status: task.status === "Done" ? "To Do" : "Done",
            })}

          >

            {task.status === "Done" ? "✓" : ""}

          </button>



          <div className="task-title">

            <strong

              className={task.status === "Done" ? "struck" : ""}

            >

              {task.title}

            </strong>

            <small>{task.description || "C2Flow AI workspace"}</small>

          </div>



          <select
            className={`priority ${task.priority.toLowerCase()}`}
            aria-label={`Priority for ${task.title}`}
            value={task.priority}
            onChange={(event) => updateTask(task.id, { priority: event.target.value })}
          >
            <option>Low</option>
            <option>Medium</option>
            <option>High</option>
          </select>



          <span

            className={`task-status ${

              task.status === "Done" ? "status-done" : ""

            }`}

          >

            {task.status}

          </span>



          <button

            className="delete-btn"

            aria-label={`Delete ${task.title}`}

            onClick={() => deleteTask(task.id)}

          >

            <Trash2 size={15} />

          </button>

        </div>

      ))}

    </div>

  );

}
