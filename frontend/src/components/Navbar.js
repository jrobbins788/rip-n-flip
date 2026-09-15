import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Zap, Menu, X, User, LogOut, Download } from 'lucide-react';
import { useEffect, useState } from 'react';
import { onInstallAvailability, promptInstall, isStandalone } from '../lib/pwa';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

export default function Navbar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [installAvail, setInstallAvail] = useState(false);
  const [standalone] = useState(() => isStandalone());

  useEffect(() => {
    return onInstallAvailability(({ available }) => setInstallAvail(!!available));
  }, []);

  const handleInstall = async () => {
    await promptInstall();
  };

  const showInstall = installAvail && !standalone;

  const navLinks = [
    { path: '/analyzer', label: 'ANALYZER', accent: 'green' },
    { path: '/predictor', label: 'PREDICT' },
    { path: '/case', label: 'BINDER' },
    { path: '/binders', label: 'GALLERY' },
    { path: '/marketplace', label: 'MARKET' },
  ];

  const isActive = (path) => location.pathname === path;

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass-dark border-b border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 group" data-testid="nav-logo">
            <img
              src="/logo.png"
              alt="Rip N' Flip"
              className="w-11 h-11 object-contain"
              style={{ filter: 'drop-shadow(0 0 12px rgba(57,255,20,0.45))' }}
            />
            <span className="sr-only">Rip N' Flip</span>
          </Link>

          {/* Desktop Nav Links */}
          <div className="hidden md:flex items-center gap-8">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                data-testid={`nav-${link.label.toLowerCase()}`}
                className={`nav-link font-heading text-lg tracking-wider transition-colors relative ${
                  isActive(link.path)
                    ? (link.accent === 'green' ? 'text-[#39FF14] active' : 'text-[#00F0FF] active')
                    : link.accent === 'green'
                    ? 'text-[#39FF14] hover:text-[#39FF14]/80'
                    : 'text-white/70 hover:text-white'
                }`}
                style={link.accent === 'green' && !isActive(link.path) ? { textShadow: '0 0 8px rgba(57,255,20,0.4)' } : undefined}
              >
                {link.label}
                {link.soon && (
                  <span className="absolute -top-2 -right-6 text-[8px] font-mono px-1 py-0.5 bg-[#FF0099]/20 text-[#FF0099] border border-[#FF0099]/40 tracking-widest">
                    SOON
                  </span>
                )}
              </Link>
            ))}
          </div>

          {/* Auth Buttons */}
          <div className="hidden md:flex items-center gap-3">
            {showInstall && (
              <Button
                onClick={handleInstall}
                variant="ghost"
                data-testid="nav-install-app"
                className="text-[#39FF14] hover:text-[#39FF14] hover:bg-[#39FF14]/10 font-heading tracking-wider gap-2"
                title="Install Rip N' Flip as an app"
              >
                <Download className="w-4 h-4" />
                INSTALL APP
              </Button>
            )}
            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button 
                    variant="ghost" 
                    className="flex items-center gap-2 text-white hover:text-[#00F0FF]"
                    data-testid="user-menu-trigger"
                  >
                    <div className="w-8 h-8 rounded-full bg-[#00F0FF]/20 border border-[#00F0FF]/50 flex items-center justify-center">
                      {user.picture ? (
                        <img src={user.picture} alt={user.name} className="w-full h-full rounded-full object-cover" />
                      ) : (
                        <User className="w-4 h-4 text-[#00F0FF]" />
                      )}
                    </div>
                    <span className="font-medium">{user.name?.split(' ')[0]}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="bg-[#0a0a0a] border-[#27272a]">
                  <DropdownMenuItem asChild>
                    <Link to="/vault" className="flex items-center gap-2 cursor-pointer" data-testid="nav-vault">
                      <User className="w-4 h-4" />
                      My Vault
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link to="/sell" className="flex items-center gap-2 cursor-pointer" data-testid="nav-sell">
                      <Zap className="w-4 h-4" />
                      Sell Cards
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleLogout} className="cursor-pointer text-red-400" data-testid="nav-logout">
                    <LogOut className="w-4 h-4 mr-2" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <>
                <Link to="/login" data-testid="nav-login">
                  <Button variant="ghost" className="text-white hover:text-[#00F0FF] font-heading tracking-wider">
                    LOGIN
                  </Button>
                </Link>
                <Link to="/register" data-testid="nav-register">
                  <Button className="btn-tactical bg-[#00F0FF] text-black hover:bg-[#00F0FF]/90 font-heading tracking-wider">
                    <span>JOIN</span>
                  </Button>
                </Link>
              </>
            )}
          </div>

          {/* Mobile Menu Button */}
          <button
            className="md:hidden text-white p-2"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            data-testid="mobile-menu-toggle"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden py-4 border-t border-white/10 animate-fade-in">
            <div className="flex flex-col gap-4">
              {navLinks.map((link) => (
                <Link
                  key={link.path}
                  to={link.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`font-heading text-lg tracking-wider ${
                    isActive(link.path)
                      ? (link.accent === 'green' ? 'text-[#39FF14]' : 'text-[#00F0FF]')
                      : link.accent === 'green'
                      ? 'text-[#39FF14]'
                      : 'text-white/70'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
              <div className="pt-4 border-t border-white/10 flex flex-col gap-2">
                {showInstall && (
                  <button
                    onClick={() => { handleInstall(); setMobileMenuOpen(false); }}
                    data-testid="nav-install-app-mobile"
                    className="text-[#39FF14] flex items-center gap-2 text-left font-heading tracking-wider"
                  >
                    <Download className="w-4 h-4" />
                    INSTALL APP
                  </button>
                )}
                {user ? (
                  <>
                    <Link to="/vault" onClick={() => setMobileMenuOpen(false)} className="text-white">
                      My Vault
                    </Link>
                    <Link to="/sell" onClick={() => setMobileMenuOpen(false)} className="text-white">
                      Sell Cards
                    </Link>
                    <button onClick={handleLogout} className="text-red-400 text-left">
                      Logout
                    </button>
                  </>
                ) : (
                  <>
                    <Link to="/login" onClick={() => setMobileMenuOpen(false)} className="text-white">
                      Login
                    </Link>
                    <Link to="/register" onClick={() => setMobileMenuOpen(false)} className="text-[#00F0FF]">
                      Join Now
                    </Link>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
