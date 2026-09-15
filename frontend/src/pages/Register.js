import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { Zap, Mail, Lock, User, ArrowLeft } from 'lucide-react';

export default function Register() {
  const navigate = useNavigate();
  const { register, loginWithGoogle, user } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  // Redirect if already logged in
  useEffect(() => {
    if (user) navigate('/vault', { replace: true });
  }, [user, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!name || !email || !password) {
      toast.error('Please fill in all fields');
      return;
    }

    if (password.length < 6) {
      toast.error('Password must be at least 6 characters');
      return;
    }

    setLoading(true);
    try {
      await register(email, password, name);
      toast.success("Welcome to Rip N' Flip!");
      navigate('/vault', { replace: true });
    } catch (error) {
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] noise-bg flex items-center justify-center px-4">
      <div className="absolute top-0 left-0 right-0 p-4">
        <Link to="/" className="inline-flex items-center gap-2 text-white/50 hover:text-white transition-colors">
          <ArrowLeft className="w-5 h-5" />
          <span className="font-mono text-sm">BACK</span>
        </Link>
      </div>

      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2">
            <div className="w-12 h-12 rounded-full overflow-hidden bg-transparent" style={{ boxShadow: '0 0 18px #FF0099aa' }}>
              <img src="/logo.png" alt="Rip N' Flip" className="w-full h-full object-cover block" draggable={false} />
            </div>
            <span className="font-heading text-3xl font-bold text-white tracking-tight">
              FLIP <span className="text-[#FF0099]">n'</span> <span className="text-[#00F0FF]">RIP</span>
            </span>
          </Link>
        </div>

        {/* Form Container */}
        <div className="bg-[#0a0a0a] border border-[#27272a] p-8">
          <h1 className="font-heading text-3xl font-bold text-white text-center mb-2">JOIN THE HUNT</h1>
          <p className="text-white/50 text-center mb-8">Create your collector account</p>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <Label htmlFor="name" className="text-white/60">Name</Label>
              <div className="relative mt-1">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40" />
                <Input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="pl-10 bg-[#121212] border-[#27272a] text-white h-12"
                  data-testid="register-name"
                />
              </div>
            </div>

            <div>
              <Label htmlFor="email" className="text-white/60">Email</Label>
              <div className="relative mt-1">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40" />
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="pl-10 bg-[#121212] border-[#27272a] text-white h-12"
                  data-testid="register-email"
                />
              </div>
            </div>

            <div>
              <Label htmlFor="password" className="text-white/60">Password</Label>
              <div className="relative mt-1">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40" />
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 6 characters"
                  className="pl-10 bg-[#121212] border-[#27272a] text-white h-12"
                  data-testid="register-password"
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full btn-tactical bg-[#FF0099] text-white hover:bg-[#FF0099]/90 h-12 font-heading tracking-wider"
              data-testid="register-submit"
            >
              <span>{loading ? 'CREATING ACCOUNT...' : 'CREATE ACCOUNT'}</span>
            </Button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-4 my-6">
            <div className="flex-1 border-t border-[#27272a]" />
            <span className="text-white/30 text-sm">OR</span>
            <div className="flex-1 border-t border-[#27272a]" />
          </div>

          {/* Google Login */}
          <Button
            type="button"
            onClick={loginWithGoogle}
            variant="outline"
            className="w-full border-[#27272a] text-white hover:bg-white/5 h-12"
            data-testid="google-register"
          >
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Sign up with Google
          </Button>

          {/* Login Link */}
          <p className="text-center mt-6 text-white/50">
            Already have an account?{' '}
            <Link to="/login" className="text-[#00F0FF] hover:underline" data-testid="login-link">
              Login
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
