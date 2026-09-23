"use client";

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  chat as sendChat,
  getToken,
  getStoredUser,
  msSinceLastActivity,
  endSession,
  IDLE_TIMEOUT_MS,
} from "@/lib/api";

interface Source {
  source_document: string;
  section_title: string;
  collection: string;
}

interface Message {
  id: number;
  type: "user" | "bot";
  content: string;
  sources?: Source[];
  retrieval_type?: "hybrid_rag" | "sql_rag";
}

interface User {
  username: string;
  role: string;
  collections: string[];
}

const ROLE_COLORS: Record<string, { bg: string; text: string; badge: string }> = {
  doctor: { bg: "bg-blue-900/50", text: "text-blue-200", badge: "bg-blue-500" },
  nurse: { bg: "bg-green-900/50", text: "text-green-200", badge: "bg-green-500" },
  billing_executive: { bg: "bg-purple-900/50", text: "text-purple-200", badge: "bg-purple-500" },
  technician: { bg: "bg-orange-900/50", text: "text-orange-200", badge: "bg-orange-500" },
  admin: { bg: "bg-red-900/50", text: "text-red-200", badge: "bg-red-500" },
};

const COLLECTION_COLORS: Record<string, string> = {
  general: "bg-cyan-800/50 text-cyan-200",
  clinical: "bg-blue-800/50 text-blue-200",
  nursing: "bg-green-800/50 text-green-200",
  billing: "bg-purple-800/50 text-purple-200",
  equipment: "bg-orange-800/50 text-orange-200",
};

export default function ChatPage() {
  const [user, setUser] = useState<User | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const storedUser = getStoredUser();
    if (!getToken() || !storedUser) {
      endSession();
      return;
    }

    // Idle timeout. The backend is the real enforcer (it stops refreshing the
    // token after the same interval); this just avoids showing a dead UI to
    // someone who left the tab open.
    if (msSinceLastActivity() > IDLE_TIMEOUT_MS) {
      endSession(true);
      return;
    }

    setUser(storedUser);

    const interval = setInterval(() => {
      if (msSinceLastActivity() > IDLE_TIMEOUT_MS) {
        endSession(true);
      }
    }, 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !user) return;

    const userMessage: Message = {
      id: Date.now(),
      type: "user",
      content: input,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      // No role is sent - the backend reads it from the bearer token.
      const data = await sendChat(input);
      setMessages((prev) => [...prev, {
        id: Date.now() + 1,
        type: "bot",
        content: data.answer,
        sources: data.sources,
        retrieval_type: data.retrieval_type,
      }]);
    } catch (err) {
      // A 401 already redirected to /login; anything else is shown inline.
      setMessages((prev) => [...prev, {
        id: Date.now() + 1,
        type: "bot",
        content: "Error: " + (err instanceof Error ? err.message : String(err)),
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    endSession();
  };

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
        <div className="animate-pulse text-blue-300">Loading...</div>
      </div>
    );
  }

  const roleColor = ROLE_COLORS[user.role] || ROLE_COLORS.doctor;

  return (
    <div className="h-screen overflow-hidden bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 flex">
      {/* Sidebar */}
      <div className="w-[420px] h-full bg-gradient-to-b from-slate-800/90 to-slate-900/90 backdrop-blur-xl flex flex-col border-r border-blue-400/30">
        {/* Logo */}
        <div className="p-8 border-b border-blue-400/30 text-center">
          <div className="flex items-center justify-center space-x-3">
            <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/30">
              <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-1 11h-4v4h-4v-4H6v-4h4V6h4v4h4v4z"/>
              </svg>
            </div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">MediBot</h1>
          </div>
          <p className="text-base text-blue-300/70 mt-3">Intelligent Medical Assistant</p>
        </div>

        {/* User Info */}
        <div className="p-8 border-b border-blue-400/30 text-center">
          <div className="flex flex-col items-center">
            <div className={`w-16 h-16 rounded-full ${roleColor.badge} flex items-center justify-center text-white font-bold text-2xl shadow-lg`}>
              {user.username.charAt(0).toUpperCase()}
            </div>
            <div className="mt-3">
              <p className="font-semibold text-white text-xl">{user.username}</p>
              <span className={`inline-block mt-2 px-4 py-2 ${roleColor.bg} ${roleColor.text} text-sm font-semibold rounded-full border border-white/10`}>
                {user.role.replace("_", " ")}
              </span>
            </div>
          </div>
        </div>

        {/* Accessible Collections */}
        <div className="p-8 flex-1 text-center">
          <p className="text-sm font-semibold text-blue-300/70 uppercase tracking-wider mb-4">
            Accessible Collections
          </p>
          <div className="space-y-3">
            {user.collections.map((collection) => (
              <div
                key={collection}
                className={`px-4 py-3 rounded-lg text-base font-medium ${COLLECTION_COLORS[collection] || "bg-slate-700/50 text-slate-200"} border border-white/10 text-center`}
              >
                {collection.charAt(0).toUpperCase() + collection.slice(1)}
              </div>
            ))}
          </div>
        </div>

        {/* Logout Button */}
        <div className="p-8 border-t border-blue-400/30">
          <button
            onClick={handleLogout}
            className="w-full bg-red-600/80 text-white py-4 px-4 rounded-lg text-lg font-medium hover:bg-red-500 transition-colors flex items-center justify-center space-x-2 border border-red-400/30"
          >
            <span>Logout</span>
          </button>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 h-full flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex-shrink-0 bg-slate-800/50 backdrop-blur-xl p-6 border-b border-blue-400/30 text-center">
          <h2 className="text-xl font-bold text-white">Chat with MediBot</h2>
          <p className="text-sm text-blue-300/70 mt-1">
            Ask questions about medical procedures, billing, equipment, and more.
          </p>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-gradient-to-br from-[#147CFA]/40 via-[#1060C8]/30 to-[#0A4096]/40">
          {messages.length === 0 && (
            <div className="text-center py-20">
              <div className="text-6xl mb-4">🏥</div>
              <p className="text-xl font-semibold text-white">Welcome to MediBot!</p>
              <p className="text-blue-300/70 mt-2">Start a conversation by asking a question.</p>
              <div className="mt-6 space-y-2 text-sm text-blue-400/50">
                <p>Try asking:</p>
                <p className="italic">&quot;What is the IV cannula size for pediatric patients?&quot;</p>
                <p className="italic">&quot;How many claims are pending?&quot;</p>
              </div>
            </div>
          )}

          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.type === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-2xl rounded-2xl p-5 ${
                  message.type === "user"
                    ? "bg-gradient-to-r from-blue-600 to-cyan-500 text-white rounded-br-md shadow-lg shadow-blue-500/20"
                    : "bg-slate-800/80 backdrop-blur-xl border border-blue-400/30 rounded-bl-md shadow-lg"
                }`}
              >
                {/* Bot Avatar */}
                {message.type === "bot" && (
                  <div className="flex items-center space-x-2 mb-3 pb-3 border-b border-blue-400/30">
                    <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-full flex items-center justify-center">
                      <span className="text-white font-bold text-sm">M</span>
                    </div>
                    <span className="font-semibold text-white">MediBot</span>
                    {message.retrieval_type && (
                      <span
                        className={`ml-auto px-3 py-1 text-xs font-semibold rounded-full ${
                          message.retrieval_type === "sql_rag"
                            ? "bg-purple-900/50 text-purple-200 border border-purple-500/30"
                            : "bg-green-900/50 text-green-200 border border-green-500/30"
                        }`}
                      >
                        {message.retrieval_type === "sql_rag" ? "SQL RAG" : "Hybrid RAG"}
                      </span>
                    )}
                  </div>
                )}

                {/* Message Content */}
                {message.type === "user" ? (
                  <p className="whitespace-pre-wrap leading-relaxed text-white">
                    {message.content}
                  </p>
                ) : (
                  <div className="prose prose-sm prose-invert max-w-none text-slate-200">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                  </div>
                )}

                {/* Sources */}
                {message.sources && message.sources.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-blue-400/30">
                    <p className="text-xs font-semibold text-blue-300/70 uppercase tracking-wider mb-3">Sources</p>
                    <div className="space-y-2">
                      {message.sources.map((source, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between bg-slate-700/50 p-3 rounded-lg text-sm border border-white/5"
                        >
                          <div>
                            <span className="font-semibold text-white">{source.source_document}</span>
                            <span className="text-blue-300/70 ml-2">- {source.section_title}</span>
                          </div>
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${COLLECTION_COLORS[source.collection] || "bg-slate-600 text-slate-200"}`}>
                            {source.collection}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Loading Indicator */}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-slate-800/80 backdrop-blur-xl border border-blue-400/30 rounded-2xl rounded-bl-md p-5 shadow-lg">
                <div className="flex items-center space-x-2 mb-3">
                  <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-full flex items-center justify-center">
                    <span className="text-white font-bold text-sm">M</span>
                  </div>
                  <span className="font-semibold text-white">MediBot</span>
                </div>
                <div className="flex space-x-2">
                  <div className="w-3 h-3 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <div className="w-3 h-3 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <div className="w-3 h-3 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="flex-shrink-0 bg-slate-800/50 backdrop-blur-xl border-t border-blue-400/30 p-6">
          <form onSubmit={handleSubmit} className="flex space-x-4">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your question here..."
              className="flex-1 px-5 py-4 border border-[#147CFA]/50 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#147CFA] focus:border-transparent text-white bg-[#147CFA]/30 placeholder-blue-200/60"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-gradient-to-r from-blue-600 to-cyan-500 text-white px-8 py-4 rounded-xl font-semibold hover:from-blue-500 hover:to-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-blue-500/30"
            >
              {loading ? "Sending..." : "Send"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
