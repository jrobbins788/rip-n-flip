import { useEffect, useRef, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, useNavigate, Link } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";

// Pages
import Landing from "./pages/Landing";
import KnowledgeHub from "./pages/KnowledgeHub";
import Terminology from "./pages/Terminology";
import PackFinder from "./pages/PackFinder";
import Marketplace from "./pages/Marketplace";
import ListingDetail from "./pages/ListingDetail";
import CreateListing from "./pages/CreateListing";
import Profile from "./pages/Profile";
import Login from "./pages/Login";
import Register from "./pages/Register";
import AuthCallback from "./pages/AuthCallback";
import PaymentSuccess from "./pages/PaymentSuccess";
import FanaticChat from "./pages/FanaticChat";
import Analyzer from "./pages/Analyzer";
import Predictor from "./pages/Predictor";
import Admin from "./pages/Admin";
import AdminLogin from "./pages/AdminLogin";
import DisplayCase from "./pages/DisplayCase";
import PublicGallery from "./pages/PublicGallery";
import PublicBinder from "./pages/PublicBinder";

// Components
import FanaticBot from "./components/FanaticBot";
import DethroneBanner from "./components/DethroneBanner";

// Context
import { AuthProvider } from "./context/AuthContext";

function AppRouter() {
  const location = useLocation();
  
  // Check URL fragment for session_id synchronously during render
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/hub" element={<KnowledgeHub />} />
      <Route path="/terminology" element={<Terminology />} />
      <Route path="/packs" element={<PackFinder />} />
      <Route path="/marketplace" element={<Marketplace />} />
      <Route path="/marketplace/:id" element={<ListingDetail />} />
      <Route path="/sell" element={<CreateListing />} />
      <Route path="/vault" element={<Profile />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/payment-success" element={<PaymentSuccess />} />
      <Route path="/chat" element={<FanaticChat />} />
      <Route path="/analyzer" element={<Analyzer />} />
      <Route path="/predictor" element={<Predictor />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/case" element={<DisplayCase />} />
      <Route path="/binders" element={<PublicGallery />} />
      <Route path="/binders/:userId" element={<PublicBinder />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App min-h-screen bg-[#050505]">
      <BrowserRouter>
        <AuthProvider>
          <DethroneBanner />
          <AppRouter />
          <FanaticBot />
          <Toaster richColors position="top-right" />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
