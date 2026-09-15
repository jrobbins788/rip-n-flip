import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { Button } from '@/components/ui/button';
import { CheckCircle, XCircle, Loader2, ShoppingBag, ArrowRight } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function PaymentSuccess() {
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('loading'); // loading, success, failed
  const [paymentData, setPaymentData] = useState(null);
  const sessionId = searchParams.get('session_id');

  useEffect(() => {
    if (sessionId) {
      pollPaymentStatus(sessionId);
    } else {
      setStatus('failed');
    }
  }, [sessionId]);

  const pollPaymentStatus = async (sid, attempts = 0) => {
    const maxAttempts = 5;
    const pollInterval = 2000;

    if (attempts >= maxAttempts) {
      setStatus('failed');
      return;
    }

    try {
      const response = await fetch(`${API}/payments/status/${sid}`, {
        credentials: 'include'
      });
      
      if (!response.ok) throw new Error('Failed to check payment status');

      const data = await response.json();
      setPaymentData(data);

      if (data.payment_status === 'paid') {
        setStatus('success');
        return;
      } else if (data.status === 'expired' || data.status === 'failed') {
        setStatus('failed');
        return;
      }

      // Continue polling
      setTimeout(() => pollPaymentStatus(sid, attempts + 1), pollInterval);
    } catch (error) {
      console.error('Error checking payment status:', error);
      if (attempts < maxAttempts - 1) {
        setTimeout(() => pollPaymentStatus(sid, attempts + 1), pollInterval);
      } else {
        setStatus('failed');
      }
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      
      <main className="pt-24 pb-12 px-4 flex items-center justify-center min-h-[80vh]">
        <div className="max-w-md w-full">
          {status === 'loading' && (
            <div className="text-center bg-[#0a0a0a] border border-[#27272a] p-12">
              <Loader2 className="w-16 h-16 text-[#00F0FF] mx-auto mb-6 animate-spin" />
              <h1 className="font-heading text-2xl font-bold text-white mb-2">PROCESSING PAYMENT</h1>
              <p className="text-white/50">Please wait while we confirm your purchase...</p>
            </div>
          )}

          {status === 'success' && (
            <div className="text-center bg-[#0a0a0a] border border-[#39FF14]/50 p-12">
              <div className="w-20 h-20 bg-[#39FF14]/20 rounded-full flex items-center justify-center mx-auto mb-6 border-2 border-[#39FF14]">
                <CheckCircle className="w-12 h-12 text-[#39FF14]" />
              </div>
              <h1 className="font-heading text-3xl font-bold text-white mb-2">PAYMENT SUCCESSFUL!</h1>
              <p className="text-white/50 mb-6">Your purchase has been confirmed. The seller will be notified.</p>
              
              {paymentData && (
                <div className="bg-[#121212] p-4 mb-6 text-left">
                  <div className="flex justify-between mb-2">
                    <span className="text-white/50">Amount Paid</span>
                    <span className="font-mono text-[#39FF14]">
                      ${(paymentData.amount_total / 100).toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-white/50">Status</span>
                    <span className="text-[#39FF14]">Paid</span>
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-3">
                <Link to="/vault" data-testid="go-to-vault">
                  <Button className="w-full bg-[#39FF14] text-black hover:bg-[#39FF14]/90 font-heading tracking-wider">
                    <span className="flex items-center gap-2">
                      VIEW IN VAULT <ArrowRight className="w-5 h-5" />
                    </span>
                  </Button>
                </Link>
                <Link to="/marketplace" data-testid="continue-shopping">
                  <Button variant="outline" className="w-full border-[#27272a] text-white hover:bg-white/5">
                    <span className="flex items-center gap-2">
                      <ShoppingBag className="w-5 h-5" /> CONTINUE SHOPPING
                    </span>
                  </Button>
                </Link>
              </div>
            </div>
          )}

          {status === 'failed' && (
            <div className="text-center bg-[#0a0a0a] border border-red-500/50 p-12">
              <div className="w-20 h-20 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-6 border-2 border-red-500">
                <XCircle className="w-12 h-12 text-red-500" />
              </div>
              <h1 className="font-heading text-3xl font-bold text-white mb-2">PAYMENT FAILED</h1>
              <p className="text-white/50 mb-6">
                Something went wrong with your payment. Please try again or contact support.
              </p>

              <div className="flex flex-col gap-3">
                <Link to="/marketplace" data-testid="return-to-market">
                  <Button className="w-full bg-[#FF0099] text-white hover:bg-[#FF0099]/90 font-heading tracking-wider">
                    <span>RETURN TO MARKETPLACE</span>
                  </Button>
                </Link>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
