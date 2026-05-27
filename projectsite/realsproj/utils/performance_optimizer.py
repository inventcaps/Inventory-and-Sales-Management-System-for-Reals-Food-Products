from django.core.cache import cache
from django.db import connection
from django.db.models import Prefetch
from functools import wraps
import hashlib
import json
import time
import logging

logger = logging.getLogger(__name__)

class SupabasePerformanceOptimizer:
    """Utility class for optimizing database performance with Supabase"""
    
    @staticmethod
    def cache_query_result(timeout=300, key_prefix=""):
        """Decorator to cache database query results"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                args_str = str(args) + str(sorted(kwargs.items()))
                cache_key = f"{key_prefix}query_{func.__name__}_{hashlib.md5(args_str.encode()).hexdigest()}"
                
                # Try to get from cache first
                start_time = time.time()
                result = cache.get(cache_key)
                
                if result is not None:
                    cache_time = time.time() - start_time
                    logger.info(f"⚡ Cache HIT for {func.__name__} ({cache_time*1000:.2f}ms)")
                    return result
                
                # Execute function and cache result
                db_start = time.time()
                result = func(*args, **kwargs)
                db_time = time.time() - db_start
                
                # Cache the result
                cache.set(cache_key, result, timeout)
                logger.info(f"🔄 Cache MISS for {func.__name__} - DB query: {db_time*1000:.2f}ms")
                return result
            return wrapper
        return decorator
    
    @staticmethod
    def optimize_queryset(queryset, select_related=None, prefetch_related=None, only_fields=None):
        """Optimize queryset with select_related, prefetch_related, and only"""
        if select_related:
            queryset = queryset.select_related(*select_related)
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)
        if only_fields:
            queryset = queryset.only(*only_fields)
        return queryset
    
    @staticmethod
    def batch_create(model_class, objects, batch_size=100):
        """Batch create objects for better performance"""
        return model_class.objects.bulk_create(objects, batch_size=batch_size)
    
    @staticmethod
    def batch_update(queryset, **kwargs):
        """Batch update objects for better performance"""
        return queryset.update(**kwargs)
    
    @staticmethod
    def get_db_performance_stats():
        """Get database performance statistics"""
        try:
            with connection.cursor() as cursor:
                # Get table sizes
                cursor.execute("""
                    SELECT 
                        schemaname,
                        tablename,
                        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                        pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
                """)
                table_stats = cursor.fetchall()
                
                # Get connection info
                cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active';")
                active_connections = cursor.fetchone()[0]
                
                return {
                    'table_stats': table_stats,
                    'active_connections': active_connections,
                    'cache_stats': cache._cache.get_stats() if hasattr(cache._cache, 'get_stats') else {}
                }
        except Exception as e:
            logger.error(f"Failed to get DB stats: {e}")
            return {}
    
    @staticmethod
    def clear_cache(pattern="*"):
        """Clear cache with optional pattern"""
        try:
            if pattern == "*":
                cache.clear()
                logger.info("🧹 Cleared all cache")
            else:
                # For pattern-based clearing, you'd need django-redis
                logger.info(f"🧹 Cache pattern clearing not implemented for: {pattern}")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

class QueryOptimizer:
    """Specific query optimizations for common operations"""
    
    @staticmethod
    @SupabasePerformanceOptimizer.cache_query_result(timeout=600, key_prefix="inventory_")
    def get_optimized_product_inventory():
        """Get product inventory with optimized queries"""
        from realsproj.models import ProductInventory
        return SupabasePerformanceOptimizer.optimize_queryset(
            ProductInventory.objects.all(),
            select_related=['product', 'product__product_type', 'product__variant', 'product__size_unit'],
            only_fields=['product__id', 'product__product_type__name', 'product__variant__name', 
                        'total_stock', 'restock_threshold']
        )
    
    @staticmethod
    @SupabasePerformanceOptimizer.cache_query_result(timeout=300, key_prefix="rawmat_")
    def get_optimized_raw_material_inventory():
        """Get raw material inventory with optimized queries"""
        from realsproj.models import RawMaterialInventory
        return SupabasePerformanceOptimizer.optimize_queryset(
            RawMaterialInventory.objects.all(),
            select_related=['material', 'material__unit'],
            only_fields=['material__id', 'material__name', 'material__unit__unit_name', 
                        'total_stock', 'reorder_threshold']
        )
    
    @staticmethod
    @SupabasePerformanceOptimizer.cache_query_result(timeout=180, key_prefix="products_")
    def get_optimized_products_list():
        """Get products list with optimized queries"""
        from realsproj.models import Products
        return SupabasePerformanceOptimizer.optimize_queryset(
            Products.objects.filter(is_archived=False),
            select_related=['product_type', 'variant', 'size', 'size_unit', 'unit_price', 'srp_price'],
            only_fields=['id', 'product_type__name', 'variant__name', 'size__size_label', 
                        'size_unit__unit_name', 'unit_price__unit_price', 'srp_price__srp_price', 
                        'date_created', 'photo']
        )

# Middleware for performance monitoring
class PerformanceMonitoringMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Log slow requests (> 1 second)
        if response_time > 1.0:
            logger.warning(f"🐌 Slow request: {request.path} took {response_time:.2f}s")
        
        # Add performance header
        response['X-Response-Time'] = f"{response_time:.3f}s"
        
        return response

# Context processor for performance stats
def performance_context(request):
    """Add performance stats to template context"""
    if request.user.is_superuser:
        try:
            stats = SupabasePerformanceOptimizer.get_db_performance_stats()
            return {'performance_stats': stats}
        except Exception:
            pass
    return {}