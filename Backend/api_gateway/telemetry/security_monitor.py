"""
VOXAR API Gateway - Security Monitor
Enterprise-grade security monitoring with threat detection and response
"""

import time
import logging
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
from datetime import datetime, timedelta
import ipaddress

logger = logging.getLogger(__name__)

class SecurityMonitor:
    """Enterprise security monitoring with intelligent threat detection"""
    
    def __init__(self, max_events: int = 10000):
        self.max_events = max_events
        
        # Security event tracking
        self.auth_attempts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.failed_auth_attempts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.security_violations: deque = deque(maxlen=max_events)
        self.blocked_ips: Dict[str, Dict[str, Any]] = {}
        
        # Threat detection thresholds
        self.auth_thresholds = {
            'max_failed_attempts': 5,       # Failed attempts before blocking
            'time_window_minutes': 15,      # Time window for failed attempts
            'block_duration_minutes': 60,   # How long to block IP
            'suspicious_rate_limit': 100    # Max requests per minute per IP
        }
        
        # Rate limiting tracking
        self.request_counts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        logger.info("✅ Security Monitor initialized")
    
    def record_authentication_attempt(self, client_ip: str, user_id: Optional[str], 
                                    success: bool, method: str, user_agent: str = None):
        """Record authentication attempt with threat analysis"""
        
        timestamp = time.time()
        
        auth_event = {
            'timestamp': timestamp,
            'client_ip': client_ip,
            'user_id': user_id,
            'success': success,
            'method': method,
            'user_agent': user_agent
        }
        
        # Record all attempts
        self.auth_attempts[client_ip].append(auth_event)
        
        if success:
            logger.info(f"✅ Successful auth: {user_id} from {client_ip}")
            
            # Clear failed attempts on successful auth
            if client_ip in self.failed_auth_attempts:
                self.failed_auth_attempts[client_ip].clear()
        else:
            # Record failed attempt
            self.failed_auth_attempts[client_ip].append(auth_event)
            logger.warning(f"❌ Failed auth attempt: {user_id or 'unknown'} from {client_ip}")
            
            # Check for brute force attack
            self._check_brute_force_attack(client_ip)
    
    def _check_brute_force_attack(self, client_ip: str):
        """Check for brute force attack patterns"""
        
        current_time = time.time()
        time_window = self.auth_thresholds['time_window_minutes'] * 60
        max_attempts = self.auth_thresholds['max_failed_attempts']
        
        # Count recent failed attempts
        recent_failures = [
            event for event in self.failed_auth_attempts[client_ip]
            if current_time - event['timestamp'] <= time_window
        ]
        
        if len(recent_failures) >= max_attempts:
            self._block_suspicious_ip(client_ip, 'brute_force_attack', {
                'failed_attempts': len(recent_failures),
                'time_window_minutes': self.auth_thresholds['time_window_minutes'],
                'recent_attempts': recent_failures[-5:]  # Last 5 attempts
            })
    
    def _block_suspicious_ip(self, client_ip: str, reason: str, evidence: Dict[str, Any]):
        """Block suspicious IP address"""
        
        block_duration = self.auth_thresholds['block_duration_minutes'] * 60
        current_time = time.time()
        
        self.blocked_ips[client_ip] = {
            'blocked_at': current_time,
            'expires_at': current_time + block_duration,
            'reason': reason,
            'evidence': evidence,
            'block_count': self.blocked_ips.get(client_ip, {}).get('block_count', 0) + 1
        }
        
        # Record security violation
        violation = {
            'timestamp': current_time,
            'type': 'ip_blocked',
            'client_ip': client_ip,
            'reason': reason,
            'evidence': evidence,
            'severity': 'high' if reason == 'brute_force_attack' else 'medium'
        }
        
        self.security_violations.append(violation)
        
        logger.error(f"🚨 SECURITY: Blocked IP {client_ip} for {reason}")
        
        # Alert security team for repeat offenders
        if self.blocked_ips[client_ip]['block_count'] >= 3:
            logger.critical(f"🚨 CRITICAL: Repeat offender IP {client_ip} blocked {self.blocked_ips[client_ip]['block_count']} times")
    
    def is_ip_blocked(self, client_ip: str) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Check if IP is currently blocked"""
        
        if client_ip not in self.blocked_ips:
            return False, None
        
        block_info = self.blocked_ips[client_ip]
        current_time = time.time()
        
        # Check if block has expired
        if current_time > block_info['expires_at']:
            del self.blocked_ips[client_ip]
            logger.info(f"IP block expired for {client_ip}")
            return False, None
        
        return True, block_info
    
    def record_security_violation(self, violation_type: str, client_ip: str, 
                                details: Dict[str, Any], severity: str = 'medium'):
        """Record security violation"""
        
        violation = {
            'timestamp': time.time(),
            'type': violation_type,
            'client_ip': client_ip,
            'details': details,
            'severity': severity
        }
        
        self.security_violations.append(violation)
        
        log_msg = f"🚨 Security violation: {violation_type} from {client_ip}"
        
        if severity == 'critical':
            logger.critical(log_msg)
        elif severity == 'high':
            logger.error(log_msg)
        else:
            logger.warning(log_msg)
        
        # Auto-block for critical violations
        if severity == 'critical':
            self._block_suspicious_ip(client_ip, violation_type, details)
    
    def record_request(self, client_ip: str, endpoint: str, method: str):
        """Record request for rate limiting analysis"""
        
        timestamp = time.time()
        
        request_event = {
            'timestamp': timestamp,
            'endpoint': endpoint,
            'method': method
        }
        
        self.request_counts[client_ip].append(request_event)
        
        # Check rate limiting
        self._check_rate_limiting(client_ip)
    
    def _check_rate_limiting(self, client_ip: str):
        """Check for rate limiting violations"""
        
        current_time = time.time()
        time_window = 60  # 1 minute window
        max_requests = self.auth_thresholds['suspicious_rate_limit']
        
        # Count requests in last minute
        recent_requests = [
            event for event in self.request_counts[client_ip]
            if current_time - event['timestamp'] <= time_window
        ]
        
        if len(recent_requests) > max_requests:
            self.record_security_violation(
                'rate_limit_exceeded',
                client_ip,
                {
                    'requests_per_minute': len(recent_requests),
                    'limit': max_requests,
                    'endpoints': list(set(req['endpoint'] for req in recent_requests[-10:]))
                },
                severity='high'
            )
    
    def get_security_summary(self) -> Dict[str, Any]:
        """Get comprehensive security summary"""
        
        current_time = time.time()
        last_24h = current_time - (24 * 3600)
        
        # Recent violations
        recent_violations = [
            v for v in self.security_violations
            if v['timestamp'] > last_24h
        ]
        
        # Active blocks
        active_blocks = {
            ip: info for ip, info in self.blocked_ips.items()
            if info['expires_at'] > current_time
        }
        
        # Authentication stats
        total_auth_attempts = sum(len(attempts) for attempts in self.auth_attempts.values())
        total_failed_attempts = sum(len(attempts) for attempts in self.failed_auth_attempts.values())
        
        # Top attacking IPs
        ip_violation_counts = defaultdict(int)
        for violation in recent_violations:
            ip_violation_counts[violation['client_ip']] += 1
        
        top_attackers = sorted(ip_violation_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Violation type breakdown
        violation_types = defaultdict(int)
        for violation in recent_violations:
            violation_types[violation['type']] += 1
        
        return {
            'summary': {
                'total_auth_attempts': total_auth_attempts,
                'total_failed_attempts': total_failed_attempts,
                'auth_success_rate': ((total_auth_attempts - total_failed_attempts) / max(total_auth_attempts, 1)) * 100,
                'violations_last_24h': len(recent_violations),
                'active_ip_blocks': len(active_blocks),
                'security_status': self._calculate_security_status(recent_violations, active_blocks)
            },
            'recent_violations': recent_violations[-20:],  # Last 20 violations
            'active_blocks': active_blocks,
            'top_attacking_ips': top_attackers,
            'violation_types': dict(violation_types),
            'thresholds': self.auth_thresholds
        }
    
    def _calculate_security_status(self, recent_violations: List[Dict], 
                                 active_blocks: Dict[str, Any]) -> str:
        """Calculate overall security status"""
        
        # Critical if >10 violations in last hour
        last_hour = time.time() - 3600
        recent_hour_violations = [v for v in recent_violations if v['timestamp'] > last_hour]
        
        if len(recent_hour_violations) > 10:
            return 'critical'
        elif len(recent_hour_violations) > 5:
            return 'high_alert'
        elif len(active_blocks) > 5:
            return 'elevated'
        elif len(recent_violations) > 0:
            return 'normal_activity'
        else:
            return 'secure'
    
    def get_ip_reputation(self, client_ip: str) -> Dict[str, Any]:
        """Get reputation information for specific IP"""
        
        current_time = time.time()
        
        # Authentication history
        auth_history = list(self.auth_attempts.get(client_ip, []))
        failed_history = list(self.failed_auth_attempts.get(client_ip, []))
        
        # Request rate
        recent_requests = [
            req for req in self.request_counts.get(client_ip, [])
            if current_time - req['timestamp'] <= 3600  # Last hour
        ]
        
        # Block history
        block_info = self.blocked_ips.get(client_ip)
        
        # Calculate reputation score (0-100)
        reputation_score = self._calculate_ip_reputation_score(
            len(auth_history), len(failed_history), len(recent_requests), block_info
        )
        
        return {
            'ip_address': client_ip,
            'reputation_score': reputation_score,
            'reputation_level': self._get_reputation_level(reputation_score),
            'total_auth_attempts': len(auth_history),
            'failed_auth_attempts': len(failed_history),
            'requests_last_hour': len(recent_requests),
            'is_currently_blocked': block_info is not None and block_info['expires_at'] > current_time,
            'block_history': block_info,
            'risk_factors': self._identify_risk_factors(client_ip, failed_history, recent_requests)
        }
    
    def _calculate_ip_reputation_score(self, total_auth: int, failed_auth: int, 
                                     recent_requests: int, block_info: Optional[Dict]) -> int:
        """Calculate IP reputation score (0-100, higher is better)"""
        
        base_score = 100
        
        # Penalize failed authentication attempts
        if total_auth > 0:
            fail_rate = failed_auth / total_auth
            base_score -= fail_rate * 30
        
        # Penalize high request rates
        if recent_requests > 100:
            base_score -= min(50, (recent_requests - 100) / 10)
        
        # Penalize blocking history
        if block_info:
            base_score -= block_info.get('block_count', 1) * 20
        
        return max(0, min(100, int(base_score)))
    
    def _get_reputation_level(self, score: int) -> str:
        """Convert reputation score to level"""
        if score >= 80:
            return 'trusted'
        elif score >= 60:
            return 'neutral'
        elif score >= 40:
            return 'suspicious'
        else:
            return 'malicious'
    
    def _identify_risk_factors(self, client_ip: str, failed_attempts: List[Dict], 
                              recent_requests: List[Dict]) -> List[str]:
        """Identify risk factors for IP address"""
        
        risk_factors = []
        
        # Check for patterns
        if len(failed_attempts) > 10:
            risk_factors.append('high_failed_auth_attempts')
        
        if len(recent_requests) > 200:
            risk_factors.append('high_request_rate')
        
        # Check for suspicious patterns in requests
        if recent_requests:
            endpoints = [req['endpoint'] for req in recent_requests]
            unique_endpoints = set(endpoints)
            
            if len(unique_endpoints) > 50:
                risk_factors.append('endpoint_scanning')
            
            if any('admin' in endpoint for endpoint in unique_endpoints):
                risk_factors.append('admin_endpoint_access')
        
        # Check IP type (this would integrate with IP intelligence services)
        try:
            ip_obj = ipaddress.ip_address(client_ip)
            if ip_obj.is_private:
                risk_factors.append('private_ip_range')
        except ValueError:
            risk_factors.append('invalid_ip_format')
        
        return risk_factors