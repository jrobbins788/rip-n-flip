import { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Zap } from 'lucide-react';

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { processOAuthSession } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Prevent double processing in StrictMode
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      try {
        // Extract session_id from URL hash
        const hash = window.location.hash;
        const params = new URLSearchParams(hash.replace('#', '?'));
        const sessionId = params.get('session_id');

        if (!sessionId) {
          console.error('No session_id found');
          navigate('/login');
          return;
        }

        // Process the OAuth session
        await processOAuthSession(sessionId);
        
        // Clear the hash and redirect to vault
        window.history.replaceState(null, '', window.location.pathname);
        navigate('/vault', { replace: true });
      } catch (error) {
        console.error('Auth callback error:', error);
        navigate('/login');
      }
    };

    processAuth();
  }, []);

  return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 rounded-full overflow-hidden bg-transparent mx-auto mb-4 animate-pulse-glow" style={{ boxShadow: '0 0 28px #39FF14cc' }}>
          <img src="/logo.png" alt="Rip N' Flip" className="w-full h-full object-cover block" draggable={false} />
        </div>
        <p className="text-[#00F0FF] font-mono animate-pulse">AUTHENTICATING...</p>
      </div>
    </div>
  );
}
