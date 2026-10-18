// Exact active-battle equations. No fast-math, quantization or saved routes.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <exception>
#include <limits>
#include <thread>
#include <condition_variable>
#include <mutex>
#include <memory>
#include <functional>
#include <vector>
#if defined(NOHIT_WITH_HIGHWAY)
#include "native_simd.hpp"
#endif
#if defined(NOHIT_WITH_PDQ)
#include <pdqsort/pdqsort.h>
#endif
#if defined(_WIN32)
#define NOMINMAX
#include <windows.h>
#else
#include <time.h>
#endif

struct JoinThreads {
    std::vector<std::thread>& threads;
    ~JoinThreads(){for(auto& thread:threads)if(thread.joinable())thread.join();}
};
struct State { double v[11]; };
// Used only where the comparator orders every entry, including its original
// index as the last tie-breaker. Stable sorts and non-total ties stay unchanged.
template<class Iterator,class Compare>static void rank_sort(Iterator begin,Iterator end,Compare less) {
#if defined(NOHIT_WITH_PDQ)
    pdqsort(begin,end,less);
#else
    std::sort(begin,end,less);
#endif
}
struct PlatformRange {
    const uint32_t* ids;int begin,end;
    int id(int slot)const{return ids?int(ids[slot]):slot;}
};
struct PlatformIndex {
    const double* rows=nullptr;int count=0;bool usable=false;
    std::array<std::vector<uint32_t>,2> sorted;
    double extent[2]={0.,0.};
    void build(const double* p,int n) {
        rows=p;count=n;usable=false;
        for(auto& axis:sorted)axis.reserve(n);
        for(int i=0;i<n;i++) {
            const double* row=p+size_t(i)*9;
            if(!row[6] && !row[7])continue;
            for(int j=0;j<4;j++)if(!std::isfinite(row[j]))return;
            for(int axis=0;axis<2;axis++) {
                sorted[axis].push_back(uint32_t(i));extent[axis]=std::max(extent[axis],row[axis+2]);
            }
        }
        for(int axis=0;axis<2;axis++)std::sort(sorted[axis].begin(),sorted[axis].end(),[&](uint32_t a,uint32_t b){
            double x=p[size_t(a)*9+axis],y=p[size_t(b)*9+axis];return x!=y?x<y:a<b;
        });
        usable=true;
    }
    PlatformRange range(double left,double top,double right,double bottom)const {
        if(!usable || !std::isfinite(left) || !std::isfinite(top) || !std::isfinite(right) || !std::isfinite(bottom))return {nullptr,0,count};
        const double low[2]={left-8.,top-8.},high[2]={right+8.,bottom+8.};
        PlatformRange best{nullptr,0,count+1};
        for(int axis=0;axis<2;axis++) {
            const auto& ids=sorted[axis];
            // Addition is monotone in the platform extent. Test the same
            // ordered endpoint sums as overlap(), without inverse arithmetic
            // or an epsilon at binary64 boundaries.
            auto begin=std::lower_bound(ids.begin(),ids.end(),low[axis],[&](uint32_t id,double value){
                return rows[size_t(id)*9+axis]+extent[axis]<value;
            });
            auto end=std::upper_bound(begin,ids.end(),high[axis],[&](double value,uint32_t id){
                return value<rows[size_t(id)*9+axis];
            });
            if(end-begin<best.end-best.begin)best={ids.data(),int(begin-ids.begin()),int(end-ids.begin())};
        }
        return best;
    }
};
static PlatformRange platform_range(const PlatformIndex* index,int count,double l,double t,double r,double b) {
    return index?index->range(l,t,r,b):PlatformRange{nullptr,0,count};
}
struct FrameCollisionIndex { int white,blue,quad_begin,quad_count; };
struct CachedQuad { double left,top,right,bottom;double axes[4][5]; };
static thread_local const double* requested_goal=nullptr;
static thread_local bool skip_policies=false;
static thread_local bool race_probes=false;
static thread_local int requested_macro_width=0,last_macro_width=0;
using ProgressCallback=void(*)(void*,int,int,int,uint64_t,uint64_t,uint64_t);
struct NativeProgress { ProgressCallback callback;void* context; };
static thread_local const NativeProgress* requested_progress=nullptr;
static thread_local uint64_t last_index_bytes=0;
static thread_local double last_index_seconds=0.;
static thread_local int last_edge_workers=1;
static thread_local int last_portfolio_workers=1;
static thread_local uint64_t last_hash_rebuilds=0;
struct DiagnosticRoute {std::vector<int64_t> word;int reason,job;};
struct Diagnostics {
    std::mutex mutex;std::vector<DiagnosticRoute> routes;int limit=32,depth=-1;bool truncated=false;
    void add(std::vector<int64_t> word,int reason,int job) {
        std::lock_guard<std::mutex> guard(mutex);
        if(int(word.size())<depth)return;
        if(int(word.size())>depth){routes.clear();depth=int(word.size());truncated=false;}
        for(const auto& route:routes)if(route.word==word)return;
        routes.push_back({std::move(word),reason,job});
        std::sort(routes.begin(),routes.end(),[](const DiagnosticRoute& a,const DiagnosticRoute& b){return a.word<b.word;});
        if(int(routes.size())>limit){routes.resize(limit);truncated=true;}
    }
};
static thread_local Diagnostics last_diagnostics;
static thread_local int requested_diagnostic_limit=32,requested_operation_weight=12,requested_held_weight=1;
static thread_local bool requested_fewest=false;
static thread_local bool requested_natural_controls=false;
static thread_local double requested_safety_margin=0.;
struct World {
    const double *env, *platforms, *white, *blue, *polygons;
    int nt, np, nw, nb, nq;
    std::vector<FrameCollisionIndex> collision_frames;
    std::vector<CachedQuad> collision_quads;
    std::vector<uint8_t> collision_cells;
    std::vector<uint32_t> collision_offsets,collision_members;
    std::vector<std::array<double,2>> gravity_axes;
    std::vector<PlatformIndex> platform_indexes;
    const double* goal=nullptr;
    const NativeProgress* progress=nullptr;
    bool race=false;int jobs=0;
    Diagnostics* diagnostics=nullptr;int operation_weight=12,held_weight=1;bool fewest=false;
    double safety_margin=0.;
    bool natural_controls=false;
    const double* axes(int t) const {return gravity_axes.empty()?nullptr:gravity_axes[t].data();}
    const double* row(int t) const { return env + t*22; }
    const double* platform(int t) const { return platforms + size_t(t)*np*9; }
    const PlatformIndex* platform_index(int t)const{return platform_indexes.empty()?nullptr:&platform_indexes[t];}
    uint64_t platform_index_bytes()const {
        uint64_t bytes=platform_indexes.capacity()*sizeof(PlatformIndex);
        for(const auto& frame:platform_indexes)for(const auto& axis:frame.sorted)bytes+=axis.capacity()*sizeof(uint32_t);
        return bytes;
    }
};
struct Stats {
    uint64_t expanded=0, generated=0, unique=0, discarded=0, workspace_bytes=0, preview_steps=0, recovery_steps=0, recoveries=0, cpu_nanoseconds=0;
    int32_t reached=0, status=0;
};
static uint64_t thread_cpu_ns() {
#if defined(_WIN32)
    FILETIME created,exit,kernel,user;
    if(!GetThreadTimes(GetCurrentThread(),&created,&exit,&kernel,&user))return 0;
    ULARGE_INTEGER k,u;k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;
    u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;
    return (k.QuadPart+u.QuadPart)*100;
#else
    timespec value{};
    if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&value)!=0)return 0;
    return uint64_t(value.tv_sec)*1000000000ULL+uint64_t(value.tv_nsec);
#endif
}
struct CpuAccounting {
    Stats& stats;uint64_t began;
    explicit CpuAccounting(Stats& value):stats(value),began(thread_cpu_ns()){}
    ~CpuAccounting(){stats.cpu_nanoseconds+=thread_cpu_ns()-began;}
};

// Persistent workers share immutable frame tensors and disjoint edge slots.
// The caller compacts/deduplicates in source parent/control order afterwards.
class EdgeTeam {
    std::mutex mutex;std::condition_variable wake,finished;
    std::vector<std::thread> threads;std::vector<uint64_t> cpu;
    std::function<void(int,int)> task;
    int total=1,count=0,remaining=0;uint64_t generation=0;bool stopping=false;
public:
    explicit EdgeTeam(int workers):cpu(workers,0),total(workers) {
        try {for(int i=1;i<workers;i++)threads.emplace_back([&,i](){
            uint64_t began=thread_cpu_ns(),seen=0;
            std::unique_lock<std::mutex> lock(mutex);
            for(;;){wake.wait(lock,[&](){return stopping || generation!=seen;});
                if(stopping)break;seen=generation;int n=count;
                lock.unlock();task(n*i/total,n*(i+1)/total);lock.lock();
                if(--remaining==0)finished.notify_one();
            }
            cpu[i]=thread_cpu_ns()-began;
        });}catch(...){stop();throw;}
    }
    void stop(){ {std::lock_guard<std::mutex> lock(mutex);stopping=true;}wake.notify_all();
        for(auto& thread:threads)if(thread.joinable())thread.join(); }
    ~EdgeTeam(){stop();}
    template<class F>void run(int n,F function){
        if(total==1 || n<128){function(0,n);return;}
        {std::lock_guard<std::mutex> lock(mutex);task=function;count=n;remaining=total-1;generation++;}
        wake.notify_all();function(0,n/total);
        std::unique_lock<std::mutex> lock(mutex);finished.wait(lock,[&](){return remaining==0;});
    }
    uint64_t finish_cpu(){stop();uint64_t value=0;for(auto n:cpu)value+=n;return value;}
};
static bool overlap(double x,double y,double l,double t,double r,double b) {
    return x+8.>=l && x-8.<=r && y+8.>=t && y-8.<=b;
}
static bool solid(double x,double y,double dy,double dir,const double* e,
                  const double* platforms,int np,double ox=0.,double oy=0.,bool old=false,const PlatformIndex* index=nullptr) {
    const int j=old?14:18;
    const double l=e[j],t=e[j+1],r=e[j+2],b=e[j+3],qx=x+ox,qy=y+oy;
    if(overlap(qx,qy,l,t,r,t+5.) || overlap(qx,qy,l,t,l+5.,b) ||
       overlap(qx,qy,l,b-5.,r,b) || overlap(qx,qy,r-5.,t,r,b))return true;
    // Both vertical platform branches are enabled in the checked-in runtime.
    if(dir==1. || dir==3.) {
    const auto candidates=platform_range(index,np,qx,qy,qx,qy);
    for(int slot=candidates.begin;slot<candidates.end;slot++) {
        const double* p=platforms+size_t(candidates.id(slot))*9;
        if(p[old?7:6] && overlap(qx,qy,p[0],p[1],p[0]+p[2],p[1]+p[3])) {
            if(dir==1. && p[1]>y && dy>=p[old?8:5] && y+8.<=p[1]+2.)return true;
            if(dir==3. && p[1]<y && dy<=p[old?8:5] && y-8.>=p[1]+p[3]-2.)return true;
        }
    }}
    return false;
}
static void clamp(double& x,double& y,const double* e,int j) {
    if(overlap(x,y,e[j],e[j+1],e[j+2],e[j+3])) {
        if(e[j]+5.>x-8.)x=e[j]+5.+8.;
        if(e[j+1]+5.>y-8.)y=e[j+1]+5.+8.;
        if(e[j+2]-5.<x+8.)x=e[j+2]-5.-8.;
        if(e[j+3]-5.<y+8.)y=e[j+3]-5.-8.;
    }
}
// Certify that every original microstep lies in empty old-frame space.
// The final sample is exactly start + displacement; ambiguous sweeps retain
// the source loop, including perpendicular wall contacts and slam effects.
static bool clear_sweep(double x0,double y0,double x1,double y1,double dy,double dir,const double* e,const double* p,int np,const PlatformIndex* index=nullptr) {
    if(!std::isfinite(x1) || !std::isfinite(y1))return false;
    double left=std::min(x0,x1),right=std::max(x0,x1),top=std::min(y0,y1),bottom=std::max(y0,y1);
    if(!(left-8.>e[14]+5. && right+8.<e[16]-5. && top-8.>e[15]+5. && bottom+8.<e[17]-5.))return false;
    if(dir==1. || dir==3.) {
    const auto candidates=platform_range(index,np,left,top,right,bottom);
    for(int slot=candidates.begin;slot<candidates.end;slot++) {
        const double* row=p+size_t(candidates.id(slot))*9;
        if(row[7] && (dir==1.?dy>=row[8]:dy<=row[8]) && right+8.>=row[0] && left-8.<=row[0]+row[2] &&
            bottom+8.>=row[1] && top-8.<=row[1]+row[3])return false;
    }}
    return true;
}
static void move_player(const State& s,const double* e,const double* p,int np,State& out,const PlatformIndex* index=nullptr) {
    double x=s.v[0],y=s.v[1],dx=s.v[2],dy=s.v[3],slammed=s.v[5],dir=s.v[7];
    double maxfall=s.v[8],slamdamage=s.v[9],damage=0.,dt=e[7];
    const double mx=dx*dt,my=dy*dt;
    if(mx!=0.) {
        const double start=x,end=start+mx;
        if(std::abs(mx)<1000000. && clear_sweep(start,y,end,y,dy,dir,e,p,np,index))x=end;
        else {
        const int count=std::max(1,int(std::floor(std::sqrt(mx*mx)+.5)));
        for(int i=1;i<=count;i++) {
            double candidate=start+mx*(double(i)/count);
            if(solid(candidate,y,dy,dir,e,p,np,0.,0.,true,index)) {
                if(slammed){slammed=0.;if(std::abs(dx)>=330. && slamdamage)damage=1.;}
                if(dx!=0.){dx=0.;x=start+mx*(double(i-1)/count);break;}
            }
            x=candidate;
        }
        }
    }
    if(my!=0.) {
        const double start=y,end=start+my;
        if(std::abs(my)<1000000. && clear_sweep(x,start,x,end,dy,dir,e,p,np,index))y=end;
        else {
        const int count=std::max(1,int(std::floor(std::sqrt(my*my)+.5)));
        for(int i=1;i<=count;i++) {
            double candidate=start+my*(double(i)/count);
            if(solid(x,candidate,dy,dir,e,p,np,0.,0.,true,index)) {
                if(slammed){slammed=0.;if(std::abs(dy)>=330. && slamdamage)damage=1.;}
                if(dy!=0.){dy=0.;y=start+my*(double(i-1)/count);break;}
            }
            y=candidate;
        }
        }
    }
    out=s;out.v[0]=x;out.v[1]=y;out.v[2]=dx;out.v[3]=dy;out.v[5]=slammed;out.v[10]=damage;
}
static void carry_platforms(double x,double& y,double& dx,double& dy,double dir,double gx,double gy,
                            const double* p,int np,const PlatformIndex* index) {
    auto touches=[&](int i) {
        const double* q=p+size_t(i)*9;
        return q[6] && overlap(x+gx*.5,y+gy*.5,q[0],q[1],q[0]+q[2],q[1]+q[3]) &&
            (dir==1.?(dy>=q[5] && y+8.<=q[1]+2.):(q[1]<y && dy<=q[5] && y-8.>=q[1]+q[3]-2.));
    };
    auto apply=[&](int i) {const double* q=p+size_t(i)*9;dx=q[4];dy=q[5];y=dir==1.?q[1]-8.05:q[1]+q[3]+8.05;};
    int after=-1;
    while(after+1<np) {
        if(!index || !index->usable) {
            for(int i=after+1;i<np;i++)if(touches(i))apply(i);
            return;
        }
        const double qx=x+gx*.5,qy=y+gy*.5;
        const auto candidates=index->range(qx,qy,qx,qy);
        if(candidates.end-candidates.begin>32) {
            for(int i=after+1;i<np;i++)if(touches(i))apply(i);
            return;
        }
        int next=np;
        for(int slot=candidates.begin;slot<candidates.end;slot++) {
            const int i=candidates.id(slot);
            if(i>after && i<next && touches(i))next=i;
        }
        if(next==np)return;
        apply(next);after=next;
        // A carry may expose another platform that was outside the old
        // query. Re-query after each update, preserving original row order.
    }
}
// Input changes occur after movement in the original engine. A parent moves
// once; its jump branches share that exact intermediate physical state.
static void finish_step(const State& s,int mask,const double* e,const double* p,int np,State& out,const double* axes=nullptr,const PlatformIndex* index=nullptr) {
    double x=s.v[0],y=s.v[1],dx=s.v[2],dy=s.v[3],slammed=s.v[5],dir=s.v[7];
    double maxfall=s.v[8],slamdamage=s.v[9],damage=s.v[10],dt=e[7];
    const int previous=int(s.v[4]);
    double mode=e[4];dir=e[5];maxfall=e[8];slamdamage=e[12];
    if(e[18]!=e[14] || e[19]!=e[15] || e[20]!=e[16] || e[21]!=e[17])clamp(x,y,e,18);
    if(e[9]){x=e[10];y=e[11];}
    const double angle=dir*(3.141592653589793/2.);
    const double gx=axes?axes[0]:std::cos(angle),gy=axes?axes[1]:std::sin(angle);
    const bool captured_slam=e[13]>=2.;
    if(e[6] || captured_slam){const double slam_speed=captured_slam?e[6]:maxfall;mode=1.;dx=gx*slam_speed;dy=gy*slam_speed;slammed=1.;}
    const double speed=(mask&16)?75.:150.;
    const int ux=((mask&2)?1:0)-((mask&1)?1:0),up=((mask&4)?1:0)-((mask&8)?1:0);
    if(mode==0.){dx=ux*speed;dy=-up*speed;}
    else {
        const int jump=dir==0.?1:dir==1.?4:dir==2.?2:8;
        if((mask&jump) && !(previous&jump) && solid(x,y,dy,dir,e,p,np,gx,gy,false,index)) {
            dx=dx-gx*180.;dy=dy-gy*180.;
        }
        if((previous&jump) && !(mask&jump)) {
            if(dir==0. && dx < -30.)dx=-30.;
            else if(dir==1. && dy < -30.)dy=-30.;
            else if(dir==2. && dx > 30.)dx=30.;
            else if(dir==3. && dy > 30.)dy=30.;
        }
        const double down=dir==0.?dx:dir==1.?dy:dir==2.?-dx:-dy;
        double gravity=0.;
        if(15.<down && down<240.)gravity=540.;
        else if(-30.<down && down<=15.)gravity=180.;
        else if(-120.<down && down<=-30.)gravity=450.;
        else if(down<=-120.)gravity=180.;
        if(!solid(x,y,dy,dir,e,p,np,gx*.2,gy*.2,false,index)) {
            dx=dx+gx*gravity*dt;dy=dy+gy*gravity*dt;
            if(dir==0. && dx>maxfall)dx=maxfall;
            else if(dir==1. && dy>maxfall)dy=maxfall;
            else if(dir==2. && dx < -maxfall)dx=-maxfall;
            else if(dir==3. && dy < -maxfall)dy=-maxfall;
        }
        if(dir==0. || dir==2.)dy=-up*speed;
        else {
            dx=0.;
            if(dir==1. || dir==3.)carry_platforms(x,y,dx,dy,dir,gx,gy,p,np,index);
            dx=dx+ux*speed;
        }
    }
    clamp(x,y,e,0);
    out={{x,y,dx,dy,double(mask),slammed,mode,dir,maxfall,slamdamage,damage}};
}
static void step(const State& s,int mask,const double* e,const double* p,int np,State& out,const double* axes=nullptr,const PlatformIndex* index=nullptr) {
    State moved;move_player(s,e,p,np,moved,index);finish_step(moved,mask,e,p,np,out,axes,index);
}
static bool quad_hit(const double* q,double x,double y,double half=2.) {
    if(!std::isfinite(q[0]))return false;
    double l=q[0],r=l,t=q[1],b=t;
    for(int i=1;i<4;i++){l=std::min(l,q[i*2]);r=std::max(r,q[i*2]);t=std::min(t,q[i*2+1]);b=std::max(b,q[i*2+1]);}
    if(x+half<l || x-half>r || y+half<t || y-half>b)return false;
    for(int i=0;i<4;i++) {
        int k=(i+1)%4;
        double ax=-(q[k*2+1]-q[i*2+1]),ay=q[k*2]-q[i*2];
        double lo=ax*q[0]+ay*q[1],hi=lo;
        for(int m=1;m<4;m++){double dot=ax*q[m*2]+ay*q[m*2+1];lo=std::min(lo,dot);hi=std::max(hi,dot);}
        double mid=ax*x+ay*y,radius=std::abs(ax)*half+std::abs(ay)*half;
        if(mid+radius<lo || mid-radius>hi)return false;
    }
    return true;
}
// Conservative cells certify only empty space or a rectangle covering the
// entire cell. Ambiguous cells always execute the original exact predicates.
// Frame partitions write disjoint tensors. Return actual helper-thread CPU;
// the calling thread is accounted independently by CpuAccounting.
template<class F>static uint64_t parallel_chunks(int n,int workers,F function) {
    workers=std::max(1,std::min(workers,n<256?1:n));
    std::vector<uint64_t> cpu(workers,0);
    std::vector<std::thread> threads;JoinThreads joiner{threads};
    for(int i=1;i<workers;i++)threads.emplace_back([&,i](){
        const uint64_t began=thread_cpu_ns();function(n*i/workers,n*(i+1)/workers);
        cpu[i]=thread_cpu_ns()-began;
    });
    function(0,n/workers);for(auto& thread:threads)thread.join();
    uint64_t sum=0;for(auto value:cpu)sum+=value;return sum;
}
// Bound the exact cached point predicate over a closed cell. Each endpoint
// uses the same multiply/add order as the point query; IEEE multiplication
// and addition are monotone. No expanded-radius rearrangement or epsilon is
// used, including at touching edges. Nonfinite axes remain conservative.
static int quad_cell_relation(const CachedQuad& q,double x,double y,double size) {
    bool inside=x+2.>=q.left && x+size-2.<=q.right && y+2.>=q.top && y+size-2.<=q.bottom;
    for(const auto& a:q.axes) {
        if(!std::isfinite(a[0]) || !std::isfinite(a[1]) || !std::isfinite(a[2]) ||
           !std::isfinite(a[3]) || !std::isfinite(a[4])){inside=false;continue;}
        const double low=a[0]*(a[0]>=0.?x:x+size)+a[1]*(a[1]>=0.?y:y+size);
        const double high=a[0]*(a[0]>=0.?x+size:x)+a[1]*(a[1]>=0.?y+size:y);
        if(!std::isfinite(low) || !std::isfinite(high)){inside=false;continue;}
        if(high+a[4]<a[2] || low-a[4]>a[3])return 0;
        if(low+a[4]<a[2] || high-a[4]>a[3])inside=false;
    }
    return inside?2:1;
}
static uint64_t prepare_collision_cells(World& w,int workers) {
    if(w.nw+w.nb<16 && w.nq<8)return 0;
    constexpr int nx=40,ny=30,cell=16,cells=nx*ny;
    w.collision_cells.assign(size_t(w.nt)*cells,0);
    w.collision_offsets.assign(w.collision_cells.size()+1,0);
    auto visit=[&](int tick,bool filling,auto emit) {
        auto mark=[&](double l,double t,double r,double b,int plane,bool rectangle,uint32_t member) {
            if(std::isnan(l)||std::isnan(t)||std::isnan(r)||std::isnan(b))return;
            if(642.<l || -2.>r || 482.<t || -2.>b)return;
            int x0=int(std::max(0.,std::min(39.,std::floor((l-2.)/cell)-1.)));
            int x1=int(std::max(0.,std::min(39.,std::floor((r+2.)/cell)+1.)));
            int y0=int(std::max(0.,std::min(29.,std::floor((t-2.)/cell)-1.)));
            int y1=int(std::max(0.,std::min(29.,std::floor((b+2.)/cell)+1.)));
            for(int iy=y0;iy<=y1;iy++)for(int ix=x0;ix<=x1;ix++) {
                const size_t key=size_t(tick)*cells+iy*nx+ix;
                if((w.collision_cells[key]&4) || (filling && !w.collision_cells[key]))continue;
                double x=ix*cell,y=iy*cell;
                if(x+cell+2.<l || x-2.>r || y+cell+2.<t || y-2.>b)continue;
                uint8_t flags=plane?2:1;
                if(rectangle && x+2.>=l && x+cell-2.<=r && y+2.>=t && y+cell-2.<=b)flags|=plane?8:4;
                if(!rectangle) {
                    const int relation=quad_cell_relation(w.collision_quads[member&0x3fffffffU],x,y,cell);
                    if(!relation)continue;
                    if(relation==2)flags|=4;
                }
                emit(iy*nx+ix,member,flags);
            }
        };
        const auto& f=w.collision_frames[tick];
        for(int plane=0;plane<2;plane++) {
            int n=plane?f.blue:f.white,stride=plane?w.nb:w.nw;
            const double* rows=(plane?w.blue:w.white)+size_t(tick)*stride*4;
            for(int i=0;i<n;i++)mark(rows[i*4],rows[i*4+1],rows[i*4+2],rows[i*4+3],plane,true,uint32_t(i)|(uint32_t(plane)<<30));
        }
        for(int i=0;i<f.quad_count;i++) {
            const auto& q=w.collision_quads[f.quad_begin+i];
            mark(q.left,q.top,q.right,q.bottom,0,false,uint32_t(f.quad_begin+i)|(2U<<30));
        }
    };
    uint64_t cpu=parallel_chunks(w.nt,workers,[&](int begin,int end){
        for(int tick=begin;tick<end;tick++)visit(tick,false,[&](int local,uint32_t,uint8_t flags){
            size_t key=size_t(tick)*cells+local;w.collision_cells[key]|=flags;w.collision_offsets[key+1]++;
        });
    });
    uint64_t total=0;
    for(size_t key=0;key<w.collision_cells.size();key++) {
        uint32_t count=(w.collision_cells[key]&4)?0:w.collision_offsets[key+1];
        total+=count;if(total>std::numeric_limits<uint32_t>::max())throw std::bad_alloc();
        w.collision_offsets[key+1]=uint32_t(total);
    }
    w.collision_members.resize(size_t(total));
    cpu+=parallel_chunks(w.nt,workers,[&](int begin,int end){
        std::array<uint32_t,cells> cursor;
        for(int tick=begin;tick<end;tick++) {
            const size_t base=size_t(tick)*cells;
            std::copy_n(w.collision_offsets.data()+base,cells,cursor.begin());
            visit(tick,true,[&](int local,uint32_t member,uint8_t){
                if(!(w.collision_cells[base+local]&4))w.collision_members[cursor[local]++]=member;
            });
        }
    });
    return cpu;
}
static uint64_t prepare_collision_index(World& w,int workers=1,bool cells=true) {
    if(w.env){w.gravity_axes.resize(w.nt);
        for(int t=0;t<w.nt;t++){double angle=w.row(t)[5]*(3.141592653589793/2.);
            w.gravity_axes[t]={{std::cos(angle),std::sin(angle)}};}}

    auto began=std::chrono::steady_clock::now();w.collision_frames.resize(w.nt);
    if(w.np>=16)w.platform_indexes.resize(w.nt);
    uint64_t cpu=parallel_chunks(w.nt,workers,[&](int begin,int end){
        for(int tick=begin;tick<end;tick++) {
            if(!w.platform_indexes.empty())w.platform_indexes[tick].build(w.platform(tick),w.np);
            auto& frame=w.collision_frames[tick];frame.white=w.nw;frame.blue=w.nb;
            const double* white=w.white+size_t(tick)*w.nw*4;
            const double* blue=w.blue+size_t(tick)*w.nb*4;
            while(frame.white && std::isnan(white[(frame.white-1)*4]))frame.white--;
            while(frame.blue && std::isnan(blue[(frame.blue-1)*4]))frame.blue--;
            frame.quad_count=0;const double* polygons=w.polygons+size_t(tick)*w.nq*8;
            for(int i=0;i<w.nq;i++)if(std::isfinite(polygons[i*8]))frame.quad_count++;
        }
    });
    size_t total=0;for(auto& frame:w.collision_frames){frame.quad_begin=int(total);total+=frame.quad_count;}
    w.collision_quads.resize(total);
    cpu+=parallel_chunks(w.nt,workers,[&](int begin,int end){
        for(int tick=begin;tick<end;tick++) {
            int destination=w.collision_frames[tick].quad_begin;
            const double* polygons=w.polygons+size_t(tick)*w.nq*8;
            for(int i=0;i<w.nq;i++) {
                const double* q=polygons+i*8;if(!std::isfinite(q[0]))continue;
                auto& item=w.collision_quads[destination++];
                item.left=item.right=q[0];item.top=item.bottom=q[1];
                for(int j=1;j<4;j++){item.left=std::min(item.left,q[j*2]);item.right=std::max(item.right,q[j*2]);
                    item.top=std::min(item.top,q[j*2+1]);item.bottom=std::max(item.bottom,q[j*2+1]);}
                for(int j=0;j<4;j++) {
                    int k=(j+1)%4;double* axis=item.axes[j];
                    axis[0]=-(q[k*2+1]-q[j*2+1]);axis[1]=q[k*2]-q[j*2];
                    axis[2]=axis[3]=axis[0]*q[0]+axis[1]*q[1];
                    for(int m=1;m<4;m++){double dot=axis[0]*q[m*2]+axis[1]*q[m*2+1];
                        axis[2]=std::min(axis[2],dot);axis[3]=std::max(axis[3],dot);}
                    axis[4]=std::abs(axis[0])*2.+std::abs(axis[1])*2.;
                }
            }
        }
    });
    if(cells)cpu+=prepare_collision_cells(w,workers);
    last_index_seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-began).count();
    return cpu;
}
static bool cached_quad_hit(const CachedQuad& q,double x,double y) {
    if(x+2.<q.left || x-2.>q.right || y+2.<q.top || y-2.>q.bottom)return false;
    for(const auto& axis:q.axes){double mid=axis[0]*x+axis[1]*y;
        if(mid+axis[4]<axis[2] || mid-axis[4]>axis[3])return false;}
    return true;
}
static bool collision(const World& w,int tick,const State& s) {
    if(s.v[10]!=0.)return true;
    const double x=s.v[0],y=s.v[1];
    if(w.safety_margin>0.) {
        // Search-only robust constraint. The ordinary index covers radius 2
        // and cannot certify this larger box; query the full geometry instead.
        const double half=2.+w.safety_margin;
        for(int plane=0;plane<2;plane++) {
            if(plane && s.v[2]==0. && s.v[3]==0.)continue;
            int n=plane?w.nb:w.nw;const double* boxes=(plane?w.blue:w.white)+size_t(tick)*n*4;
            for(int i=0;i<n;i++){const double* b=boxes+i*4;
                if(x+half>=b[0] && x-half<=b[2] && y+half>=b[1] && y-half<=b[3])return true;}
        }
        const double* polygons=w.polygons+size_t(tick)*w.nq*8;
        for(int i=0;i<w.nq;i++)if(quad_hit(polygons+i*8,x,y,half))return true;
        return false;
    }
    if(!w.collision_cells.empty() && x>=0. && x<640. && y>=0. && y<480.) {
        const size_t cell=(size_t(tick)*30+int(y/16.))*40+int(x/16.);
        const uint8_t flags=w.collision_cells[cell];
        const bool moving=s.v[2]!=0. || s.v[3]!=0.;
        if((flags&4) || (moving && (flags&8)))return true;
        if(!(flags&1) && (!moving || !(flags&2)))return false;
        for(uint32_t offset=w.collision_offsets[cell];offset<w.collision_offsets[cell+1];offset++) {
            uint32_t member=w.collision_members[offset],kind=member>>30,index=member&0x3fffffffU;
            if(kind==2){if(cached_quad_hit(w.collision_quads[index],x,y))return true;}
            else {
                if(kind && !moving)continue;
                const int stride=kind?w.nb:w.nw;
                const double* b=(kind?w.blue:w.white)+(size_t(tick)*stride+index)*4;
                if(x+2.>=b[0] && x-2.<=b[2] && y+2.>=b[1] && y-2.<=b[3])return true;
            }
        }
        return false;
    }
    for(int plane=0;plane<2;plane++) {
        if(plane && s.v[2]==0. && s.v[3]==0.)continue;
        const int stride=plane?w.nb:w.nw;
        const int n=w.collision_frames.empty()?stride:plane?w.collision_frames[tick].blue:w.collision_frames[tick].white;
        const double* boxes=(plane?w.blue:w.white)+size_t(tick)*stride*4;
#if defined(NOHIT_WITH_HIGHWAY)
        if(nohit_simd::rectangles_hit(boxes,n,x,y))return true;
#else
        for(int i=0;i<n;i++) {
            const double* b=boxes+i*4;
            if(x+2.>=b[0] && x-2.<=b[2] && y+2.>=b[1] && y-2.<=b[3])return true;
        }
#endif
    }
    if(!w.collision_frames.empty()){
        const auto& frame=w.collision_frames[tick];
        for(int i=0;i<frame.quad_count;i++)if(cached_quad_hit(w.collision_quads[frame.quad_begin+i],x,y))return true;
        return false;
    }
    const double* polys=w.polygons+size_t(tick)*w.nq*8;
    for(int i=0;i<w.nq;i++)if(quad_hit(polys+i*8,x,y))return true;
    return false;
}
static uint32_t random32(uint32_t& x){x^=x<<13;x^=x>>17;x^=x<<5;return x;}
static uint64_t word(double x){uint64_t v;std::memcpy(&v,&x,8);return v;}
static uint64_t hash_state(const State& s,int bit) {
    uint64_t h=0xcbf29ce484222325ULL;
    // Physical fields 6..10 are shared on a retained frame. Hash only the
    // varying prefix; full 11-field equality below still resolves collisions.
    for(int i=0;i<6;i++)h=(h ^ word(i==4 && bit>=0?double(int(s.v[4])&bit):s.v[i]))*0x100000001b3ULL;
    return h;
}
static uint64_t avalanche_hash(uint64_t h) {
    h=(h^(h>>30))*0xbf58476d1ce4e5b9ULL;
    h=(h^(h>>27))*0x94d049bb133111ebULL;return h^(h>>31);
}
static bool equal_state(const State& a,const State& b,int bit) {
    for(int i=0;i<11;i++)if(i==4 && bit>=0) {
        if((int(a.v[4])&bit)!=(int(b.v[4])&bit))return false;
    }else if(word(a.v[i])!=word(b.v[i]))return false;
    return true;
}
// Store only retained states for each frame, not nt * maximum_width.
// One entry has a native uint16 parent + byte mask, or three parent bytes
// for wider frontiers. No truncation: the API caps width at 100,000.
class PackedHistory {
    std::vector<std::vector<uint8_t>> rows;uint64_t allocated=0;int stride;
public:
    PackedHistory(int nt,int width):rows(nt),stride(width<=65535?3:4){}
    uint64_t bytes()const{return allocated+rows.capacity()*sizeof(rows[0]);}
    void resize(int tick,int count){auto& row=rows[tick];size_t before=row.capacity();size_t required=size_t(count)*stride;
        if(required>row.capacity())row.reserve(required);row.resize(required);
        allocated+=row.capacity()-before;}
    uint32_t parent(int tick,int index)const{const uint8_t* p=rows[tick].data()+size_t(index)*stride;
        if(stride==3){uint16_t value;std::memcpy(&value,p,2);return value;}
        return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16);}
    uint8_t mask(int tick,int index)const{return rows[tick][size_t(index)*stride+stride-1];}
    void set(int tick,int index,uint32_t parent,uint8_t mask){uint8_t* p=rows[tick].data()+size_t(index)*stride;
        if(stride==3){uint16_t value=uint16_t(parent);std::memcpy(p,&value,2);}
        else{p[0]=uint8_t(parent);p[1]=uint8_t(parent>>8);p[2]=uint8_t(parent>>16);}p[stride-1]=mask;}
};
struct Snapshot {std::array<double,4> motion;double slammed;int32_t cost;uint8_t mask;};
struct Edge {State state;uint32_t parent;int32_t cost;uint32_t tie;uint8_t mask;};
// Keep the cold rebuild out of the per-edge lookup's inlined hot path.
static void rebuild_state_hash(std::vector<int32_t>& table,const std::vector<Edge>& edges,int bit,size_t active_capacity) {
    std::fill_n(table.begin(),active_capacity,-1);const size_t mask=active_capacity-1;
    for(size_t i=0;i<edges.size();i++) {
        size_t next=avalanche_hash(hash_state(edges[i].state,bit))&mask;
        while(table[next]>=0)next=(next+1)&mask;table[next]=int(i);
    }
}
// A low-speed perpendicular wall contact can clear Slammed before a
// damaging primary-axis landing. This ranks candidates only; actual source
// movement and damage checks still decide whether any edge is admissible.
static int slam_escape_rank(const State& s,const double* e) {
    if(!s.v[9])return 0;
    if(!s.v[5])return 100;
    const bool horizontal=s.v[7]==0. || s.v[7]==2.;
    const double primary=horizontal?s.v[2]:s.v[3];
    const double perpendicular=horizontal?s.v[3]:s.v[2];
    if(std::abs(primary)<330.)return 100;
    if(std::abs(perpendicular)<1.)return -100;
    const double primary_gap=horizontal?(primary>0.?e[2]-13.-s.v[0]:s.v[0]-e[0]-13.):
        (primary>0.?e[3]-13.-s.v[1]:s.v[1]-e[1]-13.);
    const double escape_gap=horizontal?(perpendicular>0.?e[3]-13.-s.v[1]:s.v[1]-e[1]-13.):
        (perpendicular>0.?e[2]-13.-s.v[0]:s.v[0]-e[0]-13.);
    const double advantage=primary_gap/std::abs(primary)-escape_gap/std::abs(perpendicular);
    return int(std::max(-99.,std::min(99.,advantage*100.)));
}
using Bucket=std::array<int64_t,5>;
static Bucket bucket(const State& s){return {{int64_t(std::floor(s.v[0]/5.)),int64_t(std::floor(s.v[1]/5.)),int64_t(std::floor(s.v[2]/30.)),int64_t(std::floor(s.v[3]/30.)),int64_t(s.v[5])}};}
static uint64_t hash_bucket(const Bucket& b){uint64_t h=0xcbf29ce484222325ULL;for(auto x:b)h=(h ^ uint64_t(x))*0x100000001b3ULL;return h;}
// Completed portfolio runners donate their CPU slots to still-running probes.
// Total active runners plus leased helper threads never exceeds the request.
struct SpareWorkers {
    std::atomic<int> available,peak{1};std::atomic<uint64_t> hash_rebuilds{0};int limit;
    SpareWorkers(int workers,int runners):available(workers-runners),limit(workers){}
    int acquire(int maximum) {
        int free=available.load();
        while(free>0){int take=std::min(free,maximum);
            if(available.compare_exchange_weak(free,free-take))return take;}
        return 0;
    }
    void record(int count){int value=peak.load();while(value<count && !peak.compare_exchange_weak(value,count)){};}
};
using Clock=std::chrono::steady_clock;
// Each probe reads only its own counters. Python receives copied values,
// never a pointer to Stats while another native thread is writing it.
struct ProbeProgress {
    const NativeProgress* progress;int job;Stats& stats;
    Clock::time_point next=Clock::time_point::min();
    void emit(int tick,int alive,bool force=false) {
        if(!progress || !progress->callback)return;
        const auto now=Clock::now();if(!force && now<next)return;
        next=now+std::chrono::milliseconds(100);
        progress->callback(progress->context,job,tick,alive,stats.expanded,stats.discarded,stats.unique);
    }
    ~ProbeProgress(){emit(stats.reached,0,true);}
};
static bool probe(const World& w,const State& initial,const int64_t* controls,const int64_t* counts,
                  int stride,int width,uint32_t seed,int job,std::atomic<int>& best,
                  Clock::time_point deadline,int64_t* actions,Stats& stats,SpareWorkers& pool) {
    CpuAccounting cpu(stats);
    int inner_workers=1,leased=0;uint64_t hash_rebuilds=0;
    auto team=std::make_unique<EdgeTeam>(1);
    struct TeamCpu {std::unique_ptr<EdgeTeam>& team;Stats& stats;SpareWorkers& pool;int& leased;uint64_t& hash_rebuilds;
        ~TeamCpu(){pool.hash_rebuilds.fetch_add(hash_rebuilds);stats.cpu_nanoseconds+=team->finish_cpu();pool.available.fetch_add(leased);}
    } team_cpu{team,stats,pool,leased,hash_rebuilds};
    const int maxedges=width*stride;
    std::vector<State> current(width),next(width);
    std::vector<int32_t> costs(width),nextcosts(width);
    PackedHistory history(w.nt,width);const uint64_t initial_history_bytes=history.bytes();
    const int history_frames=width>=512?64:0;
    std::vector<Snapshot> snapshots(size_t(history_frames)*width);
    std::vector<int> snapshot_counts(history_frames),snapshot_ticks(history_frames,-1);
    auto capture=[&](int tick,const std::vector<State>& states,const std::vector<int32_t>& costs,int count){
        if(!history_frames)return;const int row=tick%history_frames;
        snapshot_counts[row]=count;snapshot_ticks[row]=tick;
        for(int i=0;i<count;i++){const State& s=states[i];
            snapshots[size_t(row)*width+i]={{{s.v[0],s.v[1],s.v[2],s.v[3]}},s.v[5],costs[i],uint8_t(s.v[4])};}
    };
    auto restore=[&](int tick,int index){if(tick==0)return initial;
        const Snapshot& item=snapshots[size_t(tick%history_frames)*width+index];const double* row=w.row(tick);
        return State{{item.motion[0],item.motion[1],item.motion[2],item.motion[3],double(item.mask),
            item.slammed,(row[6] || row[13]>=2.)?1.:row[4],row[5],row[8],row[12],0.}};
    };
    std::vector<Edge> staged(pool.limit>1?maxedges:0);
    std::vector<uint8_t> accepted(pool.limit>1?maxedges:0);
    std::vector<Edge> edges;edges.reserve(maxedges);
    std::vector<int> order,reps,selected;order.reserve(maxedges);reps.reserve(maxedges);selected.reserve(width);
    std::vector<uint8_t> used(maxedges);std::vector<int32_t> viability(maxedges);
    std::vector<uint64_t> cost_ties(maxedges);
    std::array<int,32> shard_counts{},shard_starts{},shard_cursor{},shard_capacities{},shard_offsets{};
    std::vector<Bucket> bucket_keys;std::vector<uint32_t> bucket_slots;
    std::vector<double> goal_scores(w.goal?maxedges:0);
    size_t capacity=8;while(capacity<size_t(maxedges)*2)capacity*=2;
    std::vector<int32_t> table(capacity,-1);
    stats.workspace_bytes=(2*size_t(width)*sizeof(State)+2*size_t(width)*4+
        initial_history_bytes+size_t(maxedges)*(sizeof(Edge)+21)+size_t(width)*4+capacity*4);
    stats.workspace_bytes+=staged.size()*(sizeof(Edge)+1)+snapshots.size()*sizeof(Snapshot)+history_frames*8+sizeof(shard_counts)*5+goal_scores.capacity()*sizeof(double);
    const uint64_t base_workspace=stats.workspace_bytes;
    auto account_history=[&](){stats.workspace_bytes=std::max(stats.workspace_bytes,base_workspace+
        history.bytes()-initial_history_bytes+bucket_keys.capacity()*sizeof(Bucket)+bucket_slots.capacity()*sizeof(uint32_t)+(table.capacity()-capacity)*sizeof(int32_t));};
    current[0]=initial;int count=1;int live_limit=(width>=2048 && job<3)?512:width;uint32_t rng=seed?seed:0x6d2b79f5U;
    ProbeProgress progress{w.progress,job,stats};
    capture(0,current,costs,count);
    auto diagnose=[&](int tick,int reason){
        if(!w.diagnostics)return;
        // Reconstruct only retained frontier paths, before recovery rewrites
        // their back-pointers. No colliding transition is included.
        std::vector<int> indices(count);for(int i=0;i<count;i++)indices[i]=i;
        std::stable_sort(indices.begin(),indices.end(),[&](int a,int b){return costs[a]<costs[b];});
        const int keep=std::min(count,w.diagnostics->limit);
        for(int i=0;i<keep;i++) {
            int parent=indices[i];std::vector<int64_t> prefix(tick);
            for(int t=tick;t>0;t--){prefix[t-1]=history.mask(t,parent);parent=int(history.parent(t,parent));}
            w.diagnostics->add(std::move(prefix),reason,job);
        }
        if(count>keep){std::lock_guard<std::mutex> guard(w.diagnostics->mutex);if(tick==w.diagnostics->depth)w.diagnostics->truncated=true;}
    };
    for(int tick=1;tick<w.nt;tick++) {
        stats.reached=tick-1;
        progress.emit(stats.reached,count);
        const int horizon=(job<3 || width<512)?0:12+12*(job%3);
        if((tick%64==1 || inner_workers==1) && (count>=512 || (horizon && count>=64))) {
            int extra=pool.acquire(std::max(0,pool.limit-inner_workers));
            if(extra){stats.cpu_nanoseconds+=team->finish_cpu();leased+=extra;inner_workers+=extra;
                team=std::make_unique<EdgeTeam>(inner_workers);pool.record(inner_workers);}
        }
        if((!w.fewest && best.load(std::memory_order_relaxed)<(w.race?w.jobs:job)) || Clock::now()>=deadline){diagnose(tick-1,1);stats.status=2;return false;}
        edges.clear();
        size_t active_capacity=8;while(active_capacity<size_t(count)*size_t(counts[tick-1])*2)active_capacity*=2;
        std::fill_n(table.begin(),active_capacity,-1);
        const double* e=w.row(tick),*p=w.platform(tick);
        const bool blue=e[4]!=0. || e[6]!=0.;
        const int jump=e[5]==0.?1:e[5]==1.?4:e[5]==2.?2:8;
        int bit=-1;
        if(tick+1<w.nt){const double* en=w.row(tick+1);bit=(en[4]!=0. || en[6]!=0.)?(en[5]==0.?1:en[5]==1.?4:en[5]==2.?2:8):0;}
        if(w.fewest)bit=-1; // Previous full mask is part of the operation-cost state.
        // IEEE positions often share all low mantissa bits (notably at 60 Hz).
        // Mix once before masking rather than first building a long linear
        // chain and then throwing the table away. Equality remains bit exact.
        auto state_slot=[&](const State& state,size_t raw_slot) {
            size_t slot=raw_slot;
            while(table[slot]>=0 && !equal_state(state,edges[table[slot]].state,bit)) {
                slot=(slot+1)&(active_capacity-1);
            }
            return slot;
        };
        if(inner_workers==1) {
        for(int parent=0;parent<count;parent++) {
            State moved;move_player(current[parent],e,p,w.np,moved,w.platform_index(tick));
            State bases[2];bool prepared[2]={false,false};int safe[2][2]={{-1,-1},{-1,-1}};
            for(int ci=0;ci<counts[tick-1];ci++) {
                int mask=int(controls[(tick-1)*stride+ci]);int branch=int(blue && (mask&jump));
                if(!prepared[branch]){finish_step(moved,branch?jump:0,e,p,w.np,bases[branch],w.axes(tick),w.platform_index(tick));prepared[branch]=true;}
                State state=bases[branch];double speed=(mask&16)?75.:150.;
                int ux=((mask&2)?1:0)-((mask&1)?1:0),up=((mask&4)?1:0)-((mask&8)?1:0);
                if(!blue){state.v[2]=ux*speed;state.v[3]=-up*speed;}
                else if(e[5]==0. || e[5]==2.)state.v[3]=-up*speed;
                else state.v[2]=bases[branch].v[2]+ux*speed;
                state.v[4]=mask;
                const int moving=int(state.v[2]!=0. || state.v[3]!=0.);
                if(safe[branch][moving]<0)safe[branch][moving]=!collision(w,tick,state);
                if(!safe[branch][moving])continue;
                stats.generated++;
                size_t slot=state_slot(state,avalanche_hash(hash_state(state,bit))&(active_capacity-1));
                if(table[slot]>=0) {
                    if(w.fewest){auto& prior=edges[table[slot]];const int cost=costs[parent]+(mask!=int(current[parent].v[4])?w.operation_weight:0)+(mask?w.held_weight:0);
                        if(cost<prior.cost)prior={state,uint32_t(parent),cost,prior.tie,uint8_t(mask)};}
                    continue;
                }
                table[slot]=int(edges.size());
                const int cost=costs[parent]+(mask!=int(current[parent].v[4])?w.operation_weight:0)+(mask?w.held_weight:0);
                edges.push_back({state,uint32_t(parent),cost,random32(rng),uint8_t(mask)});
            }
        }
        }
        else {
            team->run(count,[&](int first,int last){for(int parent=first;parent<last;parent++) {
                State moved;move_player(current[parent],e,p,w.np,moved,w.platform_index(tick));
            State bases[2];bool prepared[2]={false,false};int safe[2][2]={{-1,-1},{-1,-1}};
                for(int ci=0;ci<counts[tick-1];ci++) {
                    const int slot=parent*stride+ci;accepted[slot]=0;
                    int mask=int(controls[(tick-1)*stride+ci]);int branch=int(blue && (mask&jump));
                    if(!prepared[branch]){finish_step(moved,branch?jump:0,e,p,w.np,bases[branch],w.axes(tick),w.platform_index(tick));prepared[branch]=true;}
                    State state=bases[branch];double speed=(mask&16)?75.:150.;
                    int ux=((mask&2)?1:0)-((mask&1)?1:0),up=((mask&4)?1:0)-((mask&8)?1:0);
                    if(!blue){state.v[2]=ux*speed;state.v[3]=-up*speed;}
                    else if(e[5]==0. || e[5]==2.)state.v[3]=-up*speed;
                    else state.v[2]=bases[branch].v[2]+ux*speed;
                    state.v[4]=mask;
                    const int moving=int(state.v[2]!=0. || state.v[3]!=0.);
                    if(safe[branch][moving]<0)safe[branch][moving]=!collision(w,tick,state);
                    if(!safe[branch][moving])continue;
                    int cost=costs[parent]+(mask!=int(current[parent].v[4])?w.operation_weight:0)+(mask?w.held_weight:0);
                    staged[slot]={state,uint32_t(parent),cost,uint32_t(avalanche_hash(hash_state(state,bit))),uint8_t(mask)};accepted[slot]=1;
                }
            }});
            if(count<2048) {
                for(int parent=0;parent<count;parent++)for(int ci=0;ci<counts[tick-1];ci++) {
                    int slot=parent*stride+ci;if(!accepted[slot])continue;
                    stats.generated++;const State& state=staged[slot].state;
                    size_t hash=state_slot(state,staged[slot].tie&(active_capacity-1));
                    if(table[hash]>=0){if(w.fewest && staged[slot].cost<edges[table[hash]].cost){auto tie=edges[table[hash]].tie;edges[table[hash]]=staged[slot];edges[table[hash]].tie=tie;}continue;}
                    table[hash]=int(edges.size());staged[slot].tie=random32(rng);edges.push_back(staged[slot]);
                }
            }else {
            // Hash partitions own disjoint tables and preserve source order
            // within each list. Final compaction alone assigns the RNG ties.
            // Thus the retained first parent/control is independent of threads.
            int shards=1,shard_bits=0;while(shards<inner_workers){shards*=2;shard_bits++;}
            shard_counts.fill(0);int safe_count=0,total_capacity=0;
            for(int parent=0;parent<count;parent++)for(int ci=0;ci<counts[tick-1];ci++) {
                int slot=parent*stride+ci;if(!accepted[slot])continue;
                shard_counts[staged[slot].tie&(shards-1)]++;safe_count++;
            }
            stats.generated+=safe_count;order.resize(safe_count);int start=0;
            for(int shard=0;shard<shards;shard++) {
                shard_starts[shard]=shard_cursor[shard]=start;start+=shard_counts[shard];
                int cap=8;while(cap<shard_counts[shard]*2)cap*=2;
                shard_capacities[shard]=cap;shard_offsets[shard]=total_capacity;total_capacity+=cap;
            }
            if(size_t(total_capacity)>table.size()){if(size_t(total_capacity)>table.capacity())table.reserve(total_capacity);table.resize(total_capacity);}
            for(int parent=0;parent<count;parent++)for(int ci=0;ci<counts[tick-1];ci++) {
                int slot=parent*stride+ci;if(accepted[slot])order[shard_cursor[staged[slot].tie&(shards-1)]++]=slot;
            }
            team->run(shards*128,[&](int first,int last){for(int shard=first/128;shard<last/128;shard++) {
                int32_t* slots=table.data()+shard_offsets[shard];const uint32_t mask=uint32_t(shard_capacities[shard]-1);
                std::fill_n(slots,shard_capacities[shard],-1);
                for(int i=shard_starts[shard];i<shard_starts[shard]+shard_counts[shard];i++) {
                    int index=order[i];const Edge& edge=staged[index];uint32_t slot=(edge.tie>>shard_bits)&mask;
                    while(slots[slot]>=0 && !equal_state(edge.state,staged[slots[slot]].state,bit))slot=(slot+1)&mask;
                    if(slots[slot]>=0){if(w.fewest && edge.cost<staged[slots[slot]].cost){accepted[slots[slot]]=0;slots[slot]=index;}else accepted[index]=0;}else slots[slot]=index;
                }
            }});
            for(int parent=0;parent<count;parent++)for(int ci=0;ci<counts[tick-1];ci++) {
                int slot=parent*stride+ci;if(!accepted[slot])continue;
                staged[slot].tie=random32(rng);edges.push_back(staged[slot]);
            }
            }
        }
        stats.expanded+=count;stats.unique+=edges.size();
        if(edges.empty()) {
            diagnose(tick-1,0);
            if(live_limit<width && history_frames) {
                const int start=std::max(0,tick-513),row=start%history_frames;
                stats.workspace_bytes=std::max(stats.workspace_bytes,base_workspace+history.bytes()-initial_history_bytes+
                    bucket_keys.capacity()*sizeof(Bucket)+bucket_slots.capacity()*sizeof(uint32_t)+
                    (table.capacity()-capacity)*sizeof(int32_t)+size_t(width)*20+size_t(w.nt)*8);
                std::vector<int> origins;std::vector<uint8_t> seen(width,0);
                for(int index=0;index<count;index++) {
                    int ancestor=index;
                    for(int t=tick-1;t>start;t--)ancestor=int(history.parent(t,ancestor));
                    if(!seen[ancestor]){seen[ancestor]=1;origins.push_back(ancestor);}
                }
                std::vector<uint32_t> parents(origins.size());std::vector<uint8_t> previous_masks(origins.size());
                std::vector<int64_t> prefix(start);
                for(size_t i=0;i<origins.size();i++) {
                    int ancestor=origins[i];
                    if(start){parents[i]=history.parent(start,ancestor);previous_masks[i]=history.mask(start,ancestor);}
                    if(snapshot_ticks[row]==start) {
                        next[i]=restore(start,ancestor);nextcosts[i]=snapshots[size_t(row)*width+ancestor].cost;
                    }else {
                        for(int t=start;t>0;t--){prefix[t-1]=history.mask(t,ancestor);ancestor=int(history.parent(t,ancestor));}
                        State restored=initial;int cost=0;
                        for(int t=1;t<=start;t++) {
                            int mask=int(prefix[t-1]);cost+=(mask!=int(restored.v[4])?w.operation_weight:0)+(mask?w.held_weight:0);
                            State following;step(restored,mask,w.row(t),w.platform(t),w.np,following,w.axes(t),w.platform_index(t));restored=following;stats.recovery_steps++;
                        }
                        next[i]=restored;nextcosts[i]=cost;
                    }
                }
                // Remap just the restored row; earlier ancestry stays immutable.
                if(start)history.resize(start,int(origins.size()));
                for(size_t i=0;start && i<origins.size();i++) {
                    history.set(start,int(i),parents[i],previous_masks[i]);
                }
                count=int(origins.size());live_limit=std::min(width,live_limit*4);
                for(int t=start+1;t<tick;t++)if(snapshot_ticks[t%history_frames]==t)snapshot_ticks[t%history_frames]=-1;
                current.swap(next);costs.swap(nextcosts);capture(start,current,costs,count);account_history();tick=start;continue;
            }
            // Recover before declaring a width-pruned prefix exhausted. State
            // snapshots are reconstructed from compact ancestry only on demand.
            std::vector<uint8_t> seen(width);
            std::vector<int64_t> wordbuf(w.nt);
            std::vector<int> origins;origins.reserve(width);
            stats.workspace_bytes=std::max(stats.workspace_bytes,base_workspace+history.bytes()-initial_history_bytes+bucket_keys.capacity()*sizeof(Bucket)+bucket_slots.capacity()*sizeof(uint32_t)+size_t(width)*(1+4)+size_t(w.nt)*8);
            for(int lookback: {4,8,12,16,24,32,48,64,96,128,192,256}) {
                const int start=std::max(0,tick-lookback);
                if((!w.fewest && best.load()<(w.race?w.jobs:job)) || Clock::now()>=deadline){stats.status=2;return false;}
                origins.clear();std::fill(seen.begin(),seen.end(),0);
                const bool retained=history_frames && snapshot_ticks[start%history_frames]==start;
                if(retained){for(int i=0;i<snapshot_counts[start%history_frames];i++)origins.push_back(i);}
                else for(int index=0;index<count;index++) {
                    int ancestor=index;
                    for(int t=tick-1;t>start;t--)ancestor=int(history.parent(t,ancestor));
                    if(!seen[ancestor]){seen[ancestor]=1;origins.push_back(ancestor);}
                }
                for(int origin:origins) {
                    if((!w.fewest && best.load()<(w.race?w.jobs:job)) || Clock::now()>=deadline){stats.status=2;return false;}
                    State origin_state;int basecost=0;
                    if(retained){origin_state=restore(start,origin);basecost=snapshots[size_t(start%history_frames)*width+origin].cost;}
                    else {
                        int ancestor=origin;
                        for(int t=start;t>0;t--){wordbuf[t-1]=history.mask(t,ancestor);ancestor=int(history.parent(t,ancestor));}
                        origin_state=initial;
                        for(int t=1;t<=start;t++) {
                            int mask=int(wordbuf[t-1]);basecost+=(mask!=int(origin_state.v[4])?w.operation_weight:0)+(mask?w.held_weight:0);
                            State following;step(origin_state,mask,w.row(t),w.platform(t),w.np,following,w.axes(t),w.platform_index(t));origin_state=following;stats.recovery_steps++;
                        }
                    }
                    for(int mask=0;mask<16;mask++) {
                        if(w.natural_controls && ((mask&3)==3 || (mask&12)==12))continue;
                        State simulated=origin_state;bool safe=true;int cost=basecost;
                        for(int t=start+1;t<=tick;t++) {
                            State following;step(simulated,mask,w.row(t),w.platform(t),w.np,following,w.axes(t),w.platform_index(t));stats.recovery_steps++;
                            if(collision(w,t,following)){safe=false;break;}
                            cost+=(mask!=int(simulated.v[4])?w.operation_weight:0)+(mask?w.held_weight:0);simulated=following;
                        }
                        if(safe)edges.push_back({simulated,uint32_t(origin),cost,random32(rng),uint8_t(mask)});
                    }
                }
                if(edges.empty())continue;
                order.resize(edges.size());for(size_t i=0;i<edges.size();i++)order[i]=int(i);
                std::sort(order.begin(),order.end(),[&](int a,int b){return edges[a].cost!=edges[b].cost?edges[a].cost<edges[b].cost:edges[a].tie<edges[b].tie;});
                const int keep=std::min(live_limit,int(order.size()));
                if(history_frames)for(int t=start+1;t<tick;t++)
                    if(snapshot_ticks[t%history_frames]==t)snapshot_ticks[t%history_frames]=-1;
                for(int t=start+1;t<=tick;t++)history.resize(t,keep);
                for(int i=0;i<keep;i++) {
                    const Edge& edge=edges[order[i]];next[i]=edge.state;nextcosts[i]=edge.cost;
                    for(int t=start+1;t<=tick;t++) {
                        history.set(t,i,(t==start+1)?edge.parent:uint32_t(i),edge.mask);
                    }
                }
                current.swap(next);costs.swap(nextcosts);count=keep;stats.recoveries++;break;
            }
            if(edges.empty()){stats.status=0;return false;}
            capture(tick,current,costs,count);account_history();
            continue;
        }
        order.resize(edges.size());
        for(size_t i=0;i<order.size();i++)order[i]=int(i);
        // Independent portfolio styles may rank real exits by exact held-input
        // lookahead. Preview states are never committed as a route or proof.
        const bool group_buckets=int(edges.size())>live_limit;
        if(group_buckets){
            if(edges.size()>bucket_keys.capacity())bucket_keys.reserve(edges.size());
            if(edges.size()>bucket_slots.capacity())bucket_slots.reserve(edges.size());
            bucket_keys.resize(edges.size());bucket_slots.resize(edges.size());
            stats.workspace_bytes=std::max(stats.workspace_bytes,base_workspace+history.bytes()-initial_history_bytes+
                bucket_keys.capacity()*sizeof(Bucket)+bucket_slots.capacity()*sizeof(uint32_t));}
        std::atomic<uint64_t> preview_work{0};std::atomic<bool> interrupted{false};
        auto rank=[&](int first,int last){uint64_t work=0;
            for(int index=first;index<last;index++) {
                if(horizon && index%32==0 && ((!w.fewest && best.load()<(w.race?w.jobs:job)) || Clock::now()>=deadline)){
                    interrupted.store(true);break;}
                int score=0;
                for(int variant=0;variant<(horizon?2:0);variant++) {
                    State simulated=edges[index].state;int survived=0;
                    int mask=variant?0:edges[index].mask;
                    for(int future=tick+1;future<w.nt && future<=tick+horizon;future++) {
                        State following;step(simulated,mask,w.row(future),w.platform(future),w.np,following,w.axes(future),w.platform_index(future));work++;
                        if(collision(w,future,following))break;
                        survived++;simulated=following;
                    }
                    score=std::max(score,survived);
                }
                if(group_buckets){bucket_keys[index]=bucket(edges[index].state);bucket_slots[index]=uint32_t(avalanche_hash(hash_bucket(bucket_keys[index])));}
                cost_ties[index]=(uint64_t(uint32_t(edges[index].cost)^0x80000000U)<<32)|edges[index].tie;
                viability[index]=score+(width>=512?slam_escape_rank(edges[index].state,e):0);
                if(w.goal){double dx=edges[index].state.v[0]-w.goal[0],dy=edges[index].state.v[1]-w.goal[1];goal_scores[index]=dx*dx*w.goal[2]+dy*dy*w.goal[3];}
            }
            preview_work.fetch_add(work,std::memory_order_relaxed);
        };
        if(horizon || (group_buckets && edges.size()>=512))team->run(int(edges.size()),rank);else rank(0,int(edges.size()));
        stats.preview_steps+=preview_work.load();
        if(interrupted.load()){diagnose(tick-1,1);stats.status=2;return false;}
        auto less=[&](int a,int b){if(w.fewest && edges[a].cost!=edges[b].cost)return edges[a].cost<edges[b].cost;if(viability[a]!=viability[b])return viability[a]>viability[b];if(w.goal && goal_scores[a]!=goal_scores[b])return goal_scores[a]<goal_scores[b];if(cost_ties[a]!=cost_ties[b])return cost_ties[a]<cost_ties[b];return a<b;};
        selected.clear();
        if(int(order.size())<=live_limit) {
            rank_sort(order.begin(),order.end(),less);selected=order;
        }
        else {
            std::fill_n(table.begin(),active_capacity,-1);reps.clear();
            // Keep the same best representative per spatial bucket without
            // sorting every edge. The comparator includes a total tie break,
            // so partial selection preserves the original deterministic word.
            if(group_buckets && count>=2048 && inner_workers>1) {
                int shards=1,shard_bits=0;while(shards<inner_workers){shards*=2;shard_bits++;}
                shard_counts.fill(0);int start=0,total_capacity=0;
                for(uint32_t hash:bucket_slots)shard_counts[hash&(shards-1)]++;
                for(int shard=0;shard<shards;shard++) {
                    shard_starts[shard]=shard_cursor[shard]=start;start+=shard_counts[shard];
                    int cap=8;while(cap<shard_counts[shard]*2)cap*=2;
                    shard_capacities[shard]=cap;shard_offsets[shard]=total_capacity;total_capacity+=cap;
                }
                if(size_t(total_capacity)>table.size()){if(size_t(total_capacity)>table.capacity())table.reserve(total_capacity);table.resize(total_capacity);}
                for(size_t i=0;i<edges.size();i++)order[shard_cursor[bucket_slots[i]&(shards-1)]++]=int(i);
                reps.resize(edges.size());std::array<int,32> representative_counts{};
                team->run(shards*128,[&](int first,int last){for(int shard=first/128;shard<last/128;shard++) {
                    int32_t* slots=table.data()+shard_offsets[shard];uint32_t mask=uint32_t(shard_capacities[shard]-1);int keep=0;
                    std::fill_n(slots,shard_capacities[shard],-1);
                    for(int i=shard_starts[shard];i<shard_starts[shard]+shard_counts[shard];i++) {
                        int index=order[i];uint32_t slot=(bucket_slots[index]>>shard_bits)&mask;
                        while(slots[slot]>=0 && bucket_keys[slots[slot]]!=bucket_keys[index])slot=(slot+1)&mask;
                        if(slots[slot]<0){slots[slot]=index;reps[shard_starts[shard]+keep++]=shard_offsets[shard]+int(slot);}
                        else if(less(index,slots[slot]))slots[slot]=index;
                    }
                    representative_counts[shard]=keep;
                }});
                int keep=0;for(int shard=0;shard<shards;shard++)for(int i=0;i<representative_counts[shard];i++)
                    reps[keep++]=table[reps[shard_starts[shard]+i]];
                reps.resize(keep);
            }else {
            for(int index:order) {
                const Bucket key=group_buckets?bucket_keys[index]:bucket(edges[index].state);size_t slot=group_buckets?(bucket_slots[index]&(active_capacity-1)):hash_bucket(key)&(active_capacity-1);
                while(table[slot]>=0 && (group_buckets?bucket_keys[table[slot]]:bucket(edges[table[slot]].state))!=key)slot=(slot+1)&(active_capacity-1);
                if(table[slot]<0){table[slot]=index;reps.push_back(int(slot));}
                else if(less(index,table[slot]))table[slot]=index;
            }
            for(int& index:reps)index=table[index];
            }
            if(int(reps.size())>live_limit) {
                std::nth_element(reps.begin(),reps.begin()+live_limit,reps.end(),less);
                reps.resize(live_limit);
            }
            rank_sort(reps.begin(),reps.end(),less);selected=reps;
            const int missing=live_limit-int(selected.size());
            if(missing) {
                std::fill(used.begin(),used.begin()+edges.size(),0);
                for(int index:reps)used[index]=1;
                order.clear();
                for(size_t index=0;index<edges.size();index++)if(!used[index])order.push_back(int(index));
                if(int(order.size())>missing) {
                    std::nth_element(order.begin(),order.begin()+missing,order.end(),less);
                    order.resize(missing);
                }
                rank_sort(order.begin(),order.end(),less);
                selected.insert(selected.end(),order.begin(),order.end());
            }
        }
        stats.discarded+=edges.size()-selected.size();count=int(selected.size());
        history.resize(tick,count);
        for(int i=0;i<count;i++) {
            const Edge& edge=edges[selected[i]];next[i]=edge.state;nextcosts[i]=edge.cost;
            history.set(tick,i,edge.parent,edge.mask);
        }
        current.swap(next);costs.swap(nextcosts);
        capture(tick,current,costs,count);account_history();
    }
    int winner=0;
    auto distance=[&](int i){double dx=current[i].v[0]-w.goal[0],dy=current[i].v[1]-w.goal[1];return dx*dx*w.goal[2]+dy*dy*w.goal[3];};
    for(int i=1;i<count;i++)if((w.goal && !w.fewest)?distance(i)<distance(winner):costs[i]<costs[winner])winner=i;
    for(int tick=w.nt-1;tick>0;tick--){actions[tick-1]=history.mask(tick,winner);winner=int(history.parent(tick,winner));}
    stats.reached=w.nt-1;stats.status=1;
    if(w.race){int prior=w.jobs;best.compare_exchange_strong(prior,job);}
    else {int prior=best.load();while(job<prior && !best.compare_exchange_weak(prior,job)){};}
    return true;
}
// Coarse control decisions still execute and collision-check every source
// microtick. Failure only hands off to the ordinary one-tick frontier.
static int grounded_macro_mask(const World& w,const State& state,int intention,int tick) {
    const double* row=w.row(tick);
    if(row[4]==0. && row[6]==0.)return intention;
    const double dir=row[5];const int jump=dir==0.?1:dir==1.?4:dir==2.?2:8;
    if(!(intention&jump))return intention;
    State neutral;step(state,0,row,w.platform(tick),w.np,neutral,w.axes(tick),w.platform_index(tick));
    const double angle=neutral.v[7]*(3.141592653589793/2.);
    const bool touching=solid(neutral.v[0],neutral.v[1],neutral.v[3],neutral.v[7],row,w.platform(tick),w.np,std::cos(angle),std::sin(angle),false,w.platform_index(tick));
    if(touching==bool(int(state.v[4])&jump))intention&=~jump;
    return intention;
}
static bool macro_probe(const World& w,const State& initial,int width,int hold,uint32_t seed,
                        Clock::time_point deadline,int64_t* actions,Stats& stats,
                        int lookahead=-1,bool static_forecast=false,double bucket_size=0.,double position_bin=0.,
                        const std::atomic<bool>* cancelled=nullptr) {
    CpuAccounting cpu(stats);width=std::min(width,1024);
    if(width<1)return false;
    const int blocks=(w.nt-2+hold)/hold;
    const int horizon=lookahead<0?(width<=16?6:0):lookahead;
    const bool auto_jump=position_bin==-3. || position_bin==-4.;
    const double cell=bucket_size>0.?bucket_size:width<=16?20.:5.;
    std::vector<State> states(width),following(width);states[0]=initial;
    std::vector<int> costs(width),nextcosts(width),parents(size_t(blocks)*width);
    std::vector<uint8_t> masks(size_t(blocks)*width);
    std::vector<Edge> edges;edges.reserve(width*16);
    std::vector<int> order,selected,scores;std::vector<Bucket> buckets;
    std::vector<State> pruning_keys;std::vector<uint8_t> used;
    size_t capacity=8;while(capacity<size_t(width)*32)capacity*=2;
    std::vector<int> table(capacity);int count=1;
    stats.workspace_bytes=std::max(stats.workspace_bytes,uint64_t(width)*(176+8+blocks*5)+
        uint64_t(width)*16*(sizeof(Edge)+sizeof(Bucket)+13+(position_bin>0.?sizeof(State):0))+capacity*4);
    for(int block=0;block<blocks;block++) {
        if((cancelled && cancelled->load(std::memory_order_relaxed)) || Clock::now()>=deadline)return false;
        const int begin=block*hold+1,end=std::min(w.nt,begin+hold);
        stats.reached=begin-1;
        const double* next=end<w.nt?w.row(end):nullptr;
        const int bit=next?((next[4]!=0. || next[6]!=0.)?(next[5]==0.?1:next[5]==1.?4:next[5]==2.?2:8):0):-1;
        edges.clear();pruning_keys.clear();std::fill(table.begin(),table.end(),-1);
        const int red_masks[9]={0,1,2,4,5,6,8,9,10};
        const double* row=w.row(begin);const bool blue=row[4]!=0. || row[6]!=0.;
        const int jump=row[5]==0.?1:row[5]==1.?4:row[5]==2.?2:8;
        const int perpendicular_a=(jump==1 || jump==2)?4:1,perpendicular_b=(jump==1 || jump==2)?8:2;
        const int blue_masks[6]={0,perpendicular_a,perpendicular_b,jump,jump|perpendicular_a,jump|perpendicular_b};
        for(int parent=0;parent<count;parent++)for(int control=0;control<(blue?6:9);control++) {
            const int mask=blue?blue_masks[control]:red_masks[control];
            if(w.natural_controls && ((mask&3)==3 || (mask&12)==12))continue;
            State state=states[parent];bool safe=true;
            for(int tick=begin;tick<end;tick++) {
                const int actual=auto_jump?grounded_macro_mask(w,state,mask,tick):mask;
                State moved;step(state,actual,w.row(tick),w.platform(tick),w.np,moved,w.axes(tick),w.platform_index(tick));stats.expanded++;
                if(collision(w,tick,moved)){safe=false;break;}state=moved;
            }
            if(!safe)continue;stats.generated++;
            // Optional proposal pruning groups nearby positions while keeping
            // the retained state completely unchanged. This is not a state
            // equivalence proof and can only lose paths, never certify one.
            State key=state;
            if(position_bin>0.)for(int axis=0;axis<2;axis++) {
                double scaled=state.v[axis]/position_bin;
                if(std::isfinite(scaled) && std::abs(scaled)<1e15)key.v[axis]=std::floor(scaled+.5);
            }
            uint64_t slot=avalanche_hash(hash_state(key,bit))&(capacity-1);
            while(table[slot]>=0 && !equal_state(key,position_bin>0.?pruning_keys[table[slot]]:edges[table[slot]].state,bit))slot=(slot+1)&(capacity-1);
            if(table[slot]>=0)continue;table[slot]=int(edges.size());stats.unique++;
            const int cost=costs[parent]+(mask!=int(states[parent].v[4])?w.operation_weight:0)+(mask?(end-begin)*w.held_weight:0);
            edges.push_back({state,uint32_t(parent),cost,random32(seed),uint8_t(mask)});
            if(position_bin>0.)pruning_keys.push_back(key);
        }
        if(edges.empty())return false;
        order.resize(edges.size());for(size_t i=0;i<edges.size();i++)order[i]=int(i);
        scores.assign(edges.size(),0);
        if(horizon && int(edges.size())>width)for(size_t index=0;index<edges.size();index++) {
            if(index%32==0 && Clock::now()>=deadline)return false;
            for(int variant=0;variant<(static_forecast?1:2);variant++) {
                State current=edges[index].state;int survived=0,mask=variant?0:edges[index].mask;
                for(int tick=end;tick<std::min(w.nt,end+horizon);tick++) {
                    State next=current;
                    if(!static_forecast)step(current,mask,w.row(tick),w.platform(tick),w.np,next,w.axes(tick),w.platform_index(tick));stats.preview_steps++;
                    if(collision(w,tick,next))break;current=next;survived++;
                }
                scores[index]=std::max(scores[index],survived);
            }
        }
        auto less=[&](int a,int b){if(scores[a]!=scores[b])return scores[a]>scores[b];if(edges[a].cost!=edges[b].cost)return edges[a].cost<edges[b].cost;if(edges[a].tie!=edges[b].tie)return edges[a].tie<edges[b].tie;return a<b;};
        std::sort(order.begin(),order.end(),less);selected.clear();buckets.resize(edges.size());
        used.assign(edges.size(),0);std::fill(table.begin(),table.end(),-1);
        for(int index:order) {
            Bucket key=bucket(edges[index].state);
            key[0]=int64_t(std::floor(edges[index].state.v[0]/cell));
            key[1]=int64_t(std::floor(edges[index].state.v[1]/cell));
            if(position_bin<0. && position_bin!=-4.) {
                key[2]=position_bin==-2.?int64_t(edges[index].state.v[2]>0.)-int64_t(edges[index].state.v[2]<0.):0;
                key[3]=position_bin==-2.?int64_t(edges[index].state.v[3]>0.)-int64_t(edges[index].state.v[3]<0.):0;
            }
            buckets[index]=key;size_t slot=avalanche_hash(hash_bucket(key))&(capacity-1);
            while(table[slot]>=0 && buckets[table[slot]]!=key)slot=(slot+1)&(capacity-1);
            if(table[slot]>=0)continue;table[slot]=index;
            selected.push_back(index);used[index]=1;if(int(selected.size())==width)break;
        }
        for(int index:order) {
            if(int(selected.size())==width)break;
            if(!used[index])selected.push_back(index);
        }
        count=int(selected.size());stats.discarded+=edges.size()-count;
        for(int i=0;i<count;i++) {
            const Edge& edge=edges[selected[i]];following[i]=edge.state;nextcosts[i]=edge.cost;
            parents[size_t(block)*width+i]=int(edge.parent);masks[size_t(block)*width+i]=edge.mask;
        }
        states.swap(following);costs.swap(nextcosts);
    }
    int winner=0;for(int i=1;i<count;i++)if(costs[i]<costs[winner])winner=i;
    for(int block=blocks-1;block>=0;block--) {
        int mask=masks[size_t(block)*width+winner];winner=parents[size_t(block)*width+winner];
        for(int tick=block*hold;tick<std::min(w.nt-1,(block+1)*hold);tick++)actions[tick]=mask;
    }
    if(auto_jump) {
        State state=initial;
        for(int tick=1;tick<w.nt;tick++) {
            actions[tick-1]=grounded_macro_mask(w,state,int(actions[tick-1]),tick);
            State moved;step(state,int(actions[tick-1]),w.row(tick),w.platform(tick),w.np,moved,w.axes(tick),w.platform_index(tick));state=moved;
        }
    }
    return true;
}
extern "C" {
int nohit_macro_search(const double* initial,const double* env,int nt,const double* platforms,int np,
    const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,
    int width,int hold,uint32_t seed,double seconds,int64_t* actions,double* trace,Stats* stats,
    int lookahead,int static_forecast,double bucket_size,double position_bin) {
    try {
        if(width<1 || width>1024 || hold<1 || nt<1)return -3;
        World world{env,platforms,white,blue,polygons,nt,np,nw,nb,nq};
        {CpuAccounting cpu(*stats);stats->cpu_nanoseconds+=prepare_collision_index(world);}
        State state;std::memcpy(state.v,initial,88);
        if(collision(world,0,state))return -2;
        const auto deadline=Clock::now()+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds));
        if(!macro_probe(world,state,width,hold,seed,deadline,actions,*stats,lookahead,static_forecast,bucket_size,position_bin))return -1;
        std::memcpy(trace,state.v,88);
        for(int tick=1;tick<nt;tick++) {
            State following;step(state,int(actions[tick-1]),world.row(tick),world.platform(tick),np,following,world.axes(tick),world.platform_index(tick));
            state=following;std::memcpy(trace+tick*11,state.v,88);
        }
        stats->reached=nt-1;stats->status=1;return 0;
    }catch(...){return -3;}
}
void nohit_skip_policies(int value){skip_policies=bool(value);}
void nohit_preferences(int mode,int operation_weight,int held_weight,int limit){requested_fewest=mode==1 || mode==2;requested_natural_controls=mode>=2;requested_operation_weight=operation_weight;requested_held_weight=held_weight;requested_diagnostic_limit=std::max(1,std::min(256,limit));}
void nohit_safety_margin(double value){requested_safety_margin=std::max(0.,std::min(64.,value));}
int nohit_diagnostic_count(){return int(last_diagnostics.routes.size());}
int nohit_diagnostic_truncated(){return last_diagnostics.truncated;}
int nohit_diagnostic_route(int index,int64_t* word,int capacity,int* reason){
    if(index<0 || index>=int(last_diagnostics.routes.size()))return -1;
    const auto& route=last_diagnostics.routes[index];*reason=route.reason;
    if(capacity<int(route.word.size()))return -1;
    std::copy(route.word.begin(),route.word.end(),word);return int(route.word.size());
}
void nohit_race_probes(int value){race_probes=bool(value);}
void nohit_macro_width(int value){requested_macro_width=std::max(0,std::min(value,1024));}
int nohit_last_macro_width(){return last_macro_width;}
uint64_t nohit_last_index_bytes(){return last_index_bytes;}
double nohit_last_index_seconds(){return last_index_seconds;}
int nohit_last_edge_workers(){return last_edge_workers;}
int nohit_last_portfolio_workers(){return last_portfolio_workers;}
uint64_t nohit_last_hash_rebuilds(){return last_hash_rebuilds;}
int nohit_bones_advance(double* rows,int n,double dt) {
    int keep=0;
    for(int i=0;i<n;i++) {
        double* row=rows+size_t(i)*8;double x=row[0]+row[4]*dt,y=row[1]+row[5]*dt;
        if(row[0]!=x)row[0]=x;if(row[1]!=y)row[1]=y;
        if((row[7]==0. && row[0]>640.) || (row[7]==1. && row[1]>480.) ||
           (row[7]==2. && row[0]<-row[2]) || (row[7]==3. && row[1]<-row[3]))continue;
        if(keep!=i)std::memmove(rows+size_t(keep)*8,row,8*sizeof(double));keep++;
    }return keep;
}
int nohit_blasters_advance(double* rows,int n,double dt,double* polygons,int32_t* polygon_count) {
    int keep=0,polys=0;
    // Row order is exactly the original entity's insertion-ordered attributes.
    for(int i=0;i<n;i++) {
        double* r=rows+size_t(i)*17;
        if(r[7]>0. && (r[9]==1. || r[9]==2.))r[7]-=std::min(dt,r[7]);
        if(r[9]==0.) {
            for(int axis=0;axis<3;axis++) {
                const int slot=axis==2?6:axis+1;const double target=r[axis+3];double value=r[slot];
                if(std::abs(value-target)>=3.)value+=(target-value)*dt*10.;
                if(std::abs(value-target)<3.)value=target;
                if(axis==2 || r[slot]!=value)r[slot]=value;
            }
            if(r[1]==r[3] && r[2]==r[4] && r[6]==r[5])r[9]=1.;
        }
        if(r[9]==1. && r[7]==0.){r[9]=2.;r[7]=.1;}
        if(r[9]==2. && r[7]==0.){r[9]=3.;r[13]=1.;}
        if(r[9]==3.) {
            r[10]+=30.;const double angle=r[6]*(3.141592653589793/180.);
            const double ux=std::cos(angle),uy=std::sin(angle);
            const double width=57.*r[16],height=44.*r[15];
            const double offset=(.5-0.5087719559669495)*width;
            const double cx=r[1]+ux*offset,cy=r[2]+uy*offset;
            const double rx=(std::abs(ux)*width+std::abs(uy)*height)*.5;
            const double ry=(std::abs(uy)*width+std::abs(ux)*height)*.5;
            if(cx+rx<0. || cx-rx>640. || cy+ry<0. || cy-ry>480.)r[10]=0.;
            const double x=r[1]-ux*dt*r[10],y=r[2]-uy*dt*r[10];
            if(r[1]!=x)r[1]=x;if(r[2]!=y)r[2]=y;
            r[11]+=dt;
            if(r[11]<4./30.)r[12]+=std::floor(35.*r[15]/4.)*dt*30.;
            if(4./30.<=r[11] && r[11]<4./30.+dt)r[12]=35.*r[15];
            if(r[11]>5./30.+r[8]) {
                r[12]*=std::pow(.8,dt*30.);r[14]=100.-((r[11]-r[8])*30.-5.)*10.;
                if(r[12]<=2.)continue;
            }
            const double opacity=std::min(1.,std::max(0.,r[14]/100.));
            if(std::floor(1e6*(100.*opacity)+.5)/1e6<=80.)r[13]=0.;
        }
        if(r[13]) {
            const double angle=r[6]*(3.141592653589793/180.);
            const double ux=std::cos(angle),uy=std::sin(angle);
            const double ax=r[1]+ux*70.*r[15]/2.,ay=r[2]+uy*70.*r[15]/2.,hw=r[12]*3./8.;
            double* p=polygons+size_t(polys++)*8;
            p[0]=ax-uy*hw;p[1]=ay+ux*hw;p[2]=ax+uy*hw;p[3]=ay-ux*hw;
            p[4]=ax+1000.*ux+uy*hw;p[5]=ay+1000.*uy-ux*hw;
            p[6]=ax+1000.*ux-uy*hw;p[7]=ay+1000.*uy+ux*hw;
        }
        if(keep!=i)std::memmove(rows+size_t(keep)*17,r,17*sizeof(double));keep++;
    }
    *polygon_count=polys;return keep;
}
int nohit_bones_geometry(const double* rows,int n,double* output) {
    int whites=0;for(int i=0;i<n;i++)if(rows[size_t(i)*8+6]!=1.)whites++;
    int white=0,blue=whites;
    for(int i=0;i<n;i++) {
        const double* row=rows+size_t(i)*8;double* box=output+size_t(row[6]==1.?blue++:white++)*4;
        double x=row[0],y=row[1],r=x+row[2],b=y+row[3];
        box[0]=r<x?r:x;box[1]=b<y?b:y;box[2]=r>x?r:x;box[3]=b>y?b:y;
    }return whites;
}
int nohit_bones_geometry_clipped(const double* rows,int n,double* output,const double* bounds,int32_t* blue_count) {
    int whites=0,blues=0;
    for(int i=0;i<n;i++) {
        const double* row=rows+size_t(i)*8;
        const double x=row[0],y=row[1],r=x+row[2],b=y+row[3];
        const double l=r<x?r:x,t=b<y?b:y,right=r>x?r:x,bottom=b>y?b:y;
        if(!(l<=bounds[2] && right>=bounds[0] && t<=bounds[3] && bottom>=bounds[1]))continue;
        const int destination=row[6]==1.?n-1-blues++:whites++;
        double* box=output+size_t(destination)*4;
        box[0]=l;box[1]=t;box[2]=right;box[3]=bottom;
    }
    *blue_count=blues;return whites;
}
// ABI widths are fixed; callers validate contiguous arrays and resource limits.
int nohit_expand(const double* states,int n,const int64_t* controls,int nc,
                 const double* env,int nt,const double* platforms,int np,
                 const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,
                 int tick,int workers,double* output,int64_t* parents,int64_t* masks) {
    try {
        World world{env,platforms,white,blue,polygons,nt,np,nw,nb,nq};
        prepare_collision_index(world,workers);
        std::vector<int> counts(n);
        const double* e=world.row(tick),*p=world.platform(tick);
        const bool blue_mode=e[4]!=0. || e[6]!=0.;
        const int jump=e[5]==0.?1:e[5]==1.?4:e[5]==2.?2:8;
        auto chunk=[&](int first,int last) {
            for(int parent=first;parent<last;parent++) {
                State in,bases[2];std::memcpy(in.v,states+parent*11,88);
                bool prepared[2]={false,false};int safe[2][2]={{-1,-1},{-1,-1}},count=0;
                for(int ci=0;ci<nc;ci++) {
                    const int mask=int(controls[ci]),branch=int(blue_mode && (mask&jump));
                    if(!prepared[branch]){step(in,branch?jump:0,e,p,np,bases[branch],world.axes(tick),world.platform_index(tick));prepared[branch]=true;}
                    State state=bases[branch];const double speed=(mask&16)?75.:150.;
                    const int ux=((mask&2)?1:0)-((mask&1)?1:0),up=((mask&4)?1:0)-((mask&8)?1:0);
                    if(!blue_mode){state.v[2]=ux*speed;state.v[3]=-up*speed;}
                    else if(e[5]==0. || e[5]==2.)state.v[3]=-up*speed;
                    else state.v[2]=bases[branch].v[2]+ux*speed;
                    state.v[4]=mask;const int moving=int(state.v[2]!=0. || state.v[3]!=0.);
                    if(safe[branch][moving]<0)safe[branch][moving]=!collision(world,tick,state);
                    if(!safe[branch][moving])continue;
                    const size_t destination=size_t(parent)*nc+count++;
                    std::memcpy(output+destination*11,state.v,88);masks[destination]=mask;
                }
                counts[parent]=count;
            }
        };
        workers=std::max(1,std::min(workers,n));std::vector<std::thread> threads;JoinThreads joiner{threads};
        for(int i=1;i<workers;i++)threads.emplace_back(chunk,int(int64_t(n)*i/workers),int(int64_t(n)*(i+1)/workers));
        chunk(0,n/workers);for(auto& thread:threads)thread.join();
        size_t count=0;
        for(int parent=0;parent<n;parent++) {
            const size_t source=size_t(parent)*nc,keep=counts[parent];
            if(keep){std::memmove(output+count*11,output+source*11,keep*88);std::memmove(masks+count,masks+source,keep*8);}
            for(size_t i=0;i<keep;i++)parents[count+i]=parent;
            count+=keep;
        }
        return int(count);
    }catch(...){return -1;}
}
int nohit_rollout(const double* initial,const double* env,int nt,const double* platforms,int np,double* output) {
    State state;std::memcpy(state.v,initial,88);
    for(int tick=0;tick<nt;tick++) {
        const double* e=env+tick*22;const double angle=e[5]*(3.141592653589793/2.);
        const double axes[2]={std::cos(angle),std::sin(angle)};State following;
        const double* rows=platforms+size_t(tick)*np*9;PlatformIndex index;if(np>=16)index.build(rows,np);
        step(state,0,e,rows,np,following,axes,np>=16?&index:nullptr);state=following;
    }
    std::memcpy(output,state.v,88);return 0;
}
int nohit_step(const double* states,int n,const int64_t* masks,const double* env,const double* platforms,int np,double* output) {
    const double angle=env[5]*(3.141592653589793/2.);const double axes[2]={std::cos(angle),std::sin(angle)};
    PlatformIndex index;if(np>=16)index.build(platforms,np);
    for(int i=0;i<n;i++){State in,out;std::memcpy(in.v,states+i*11,88);step(in,int(masks[i]),env,platforms,np,out,axes,np>=16?&index:nullptr);std::memcpy(output+i*11,out.v,88);}return 0;
}
int nohit_collision(const double* states,int n,const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,uint8_t* output) {
    World world{nullptr,nullptr,white,blue,polygons,1,0,nw,nb,nq};
    prepare_collision_index(world);
    for(int i=0;i<n;i++){State s;std::memcpy(s.v,states+i*11,88);output[i]=collision(world,0,s);}return 0;
}
int nohit_collision_margin(const double* states,int n,const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,uint8_t* output,double margin) {
    World world{nullptr,nullptr,white,blue,polygons,1,0,nw,nb,nq};world.safety_margin=margin;
    for(int i=0;i<n;i++){State s;std::memcpy(s.v,states+i*11,88);output[i]=collision(world,0,s);}return 0;
}
// Minimum additional L-infinity expansion of the 4x4 heart that reaches an
// active hazard. This is sampled spatial clearance, not a dynamics guarantee.
void nohit_clearance(const double* state,const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,double* output) {
    const double x=state[0],y=state[1];double best=std::numeric_limits<double>::infinity();
    int kind=-1,index=-1,locked=0;
    for(int plane=0;plane<2;plane++)for(int i=0;i<(plane?nb:nw);i++) {
        const double* b=(plane?blue:white)+i*4;if(std::isnan(b[0]))continue;
        const double gap=std::max({0.,b[0]-x-2.,x-2.-b[2],b[1]-y-2.,y-2.-b[3]});
        if(plane && state[2]==0. && state[3]==0.){if(gap==0.)locked=1;continue;}
        if(gap<best){best=gap;kind=plane;index=i;}
    }
    for(int i=0;i<nq;i++) {
        const double* q=polygons+i*8;if(!std::isfinite(q[0]))continue;
        double l=q[0],r=l,t=q[1],b=t;
        for(int j=1;j<4;j++){l=std::min(l,q[j*2]);r=std::max(r,q[j*2]);t=std::min(t,q[j*2+1]);b=std::max(b,q[j*2+1]);}
        double gap=std::max({0.,l-x-2.,x-2.-r,t-y-2.,y-2.-b});
        for(int j=0;j<4;j++) {
            int k=(j+1)%4;double ax=-(q[k*2+1]-q[j*2+1]),ay=q[k*2]-q[j*2];
            double norm=std::abs(ax)+std::abs(ay);if(norm==0.)continue;
            double lo=ax*q[0]+ay*q[1],hi=lo;
            for(int m=1;m<4;m++){double dot=ax*q[m*2]+ay*q[m*2+1];lo=std::min(lo,dot);hi=std::max(hi,dot);}
            double mid=ax*x+ay*y;
            gap=std::max(gap,std::max(lo-mid,mid-hi)/norm-2.);
        }
        if(gap<best){best=gap;kind=2;index=i;}
    }
    output[0]=best;output[1]=kind;output[2]=index;output[3]=locked;
}
// Validate a request-local proposed continuation against this newly executed
// world. A hint is never a certificate and can be rejected at any frame.
int nohit_replay(const double* initial,const int64_t* actions,const double* env,int nt,
                 const double* platforms,int np,const double* white,int nw,
                 const double* blue,int nb,const double* polygons,int nq,double* trace) {
    try {
        World world{env,platforms,white,blue,polygons,nt,np,nw,nb,nq};
        prepare_collision_index(world,1,false);
        State state;std::memcpy(state.v,initial,88);std::memcpy(trace,state.v,88);
        if(collision(world,0,state))return 0;
        for(int tick=1;tick<nt;tick++) {
            State following;step(state,int(actions[tick-1]),world.row(tick),world.platform(tick),np,following,world.axes(tick),world.platform_index(tick));
            if(collision(world,tick,following))return tick;
            state=following;std::memcpy(trace+tick*11,state.v,88);
        }
        return nt;
    }catch(...){return -1;}
}
int nohit_search(const double* initial,const double* env,int nt,const double* platforms,int np,
                 const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,
                 const int64_t* controls,const int64_t* counts,int stride,const int32_t* widths,
                 const uint32_t* seeds,int jobs,int workers,double seconds,int64_t* actions,
                 double* trace,Stats* stats,int32_t* controller_delay) {
    try {
        last_diagnostics.routes.clear();last_diagnostics.depth=-1;last_diagnostics.truncated=false;last_diagnostics.limit=requested_diagnostic_limit;
        last_edge_workers=1;last_hash_rebuilds=0;last_macro_width=0;World world{env,platforms,white,blue,polygons,nt,np,nw,nb,nq};world.goal=requested_goal;world.progress=requested_progress;world.race=race_probes;world.jobs=jobs;world.diagnostics=&last_diagnostics;world.operation_weight=requested_operation_weight;world.held_weight=requested_held_weight;world.fewest=requested_fewest;world.safety_margin=requested_safety_margin;world.natural_controls=requested_natural_controls;State state;std::memcpy(state.v,initial,88);
        {CpuAccounting index_cpu(stats[0]);stats[0].cpu_nanoseconds+=prepare_collision_index(world,workers,false);}
        last_index_bytes=world.collision_frames.size()*sizeof(FrameCollisionIndex)+world.collision_quads.size()*sizeof(CachedQuad)+
            world.collision_cells.size()+world.collision_offsets.size()*4+world.collision_members.size()*4+world.gravity_axes.size()*16+world.platform_index_bytes();
        if(collision(world,0,state)){last_diagnostics.add({},2,0);return -2;}
        auto deadline=Clock::now()+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds));
        *controller_delay=-1;
        // Cheap generic policies jump after exact ground contact. They contain
        // no attack names or routes; every accepted tick passes the same oracle.
        { CpuAccounting policy_cpu(stats[0]);
        for(int policy=0;!skip_policies && !world.fewest && !world.goal && policy<27;policy++) {
            const int delay=policy%9,steer=policy/9;
            State current=state;int grounded=0;bool safe=true;
            std::memcpy(trace,current.v,88);
            for(int tick=1;tick<nt;tick++) {
                if(Clock::now()>=deadline){last_diagnostics.add(std::vector<int64_t>(actions,actions+tick-1),1,policy);return -1;}
                const double* row=world.row(tick);int mask=0;
                State neutral;step(current,0,row,world.platform(tick),np,neutral,world.axes(tick),world.platform_index(tick));
                if(neutral.v[6]!=0.) {
                    const double dir=neutral.v[7],angle=dir*(3.141592653589793/2.);
                    const double gx=std::cos(angle),gy=std::sin(angle);
                    const int jump=dir==0.?1:dir==1.?4:dir==2.?2:8;
                    if(row[6])grounded=0;
                    const bool touching=solid(neutral.v[0],neutral.v[1],neutral.v[3],dir,row,world.platform(tick),np,gx,gy,false,world.platform_index(tick));
                    if(touching){grounded++;if(!(int(current.v[4])&jump) && grounded>delay)mask=jump;}
                    else{grounded=0;if(int(current.v[4])&jump)mask=jump;}
                }
                if(steer && neutral.v[6]!=0.) {
                    const bool vertical=neutral.v[7]==1. || neutral.v[7]==3.;
                    mask|=vertical?(steer==1?1:2):(steer==1?4:8);
                }
                if(world.natural_controls && ((mask&3)==3 || (mask&12)==12)){safe=false;break;}
                State following;step(current,mask,row,world.platform(tick),np,following,world.axes(tick),world.platform_index(tick));
                if(collision(world,tick,following)){last_diagnostics.add(std::vector<int64_t>(actions,actions+tick-1),0,policy);safe=false;break;}
                current=following;actions[tick-1]=mask;std::memcpy(trace+tick*11,current.v,88);
            }
            if(safe){*controller_delay=policy;stats[0].expanded=nt-1;stats[0].generated=nt-1;stats[0].unique=nt-1;
                stats[0].reached=nt-1;stats[0].status=1;stats[0].workspace_bytes=3*sizeof(State);return 0;}
        }
        }
        if(!skip_policies && !world.fewest && !world.goal && nt>32) {
            const auto short_deadline=std::min(deadline,Clock::now()+std::chrono::milliseconds(std::min(128,std::max(12,nt/20))));
            for(int hold: {16,8,4,2})if(macro_probe(world,state,std::min(16,*std::max_element(widths,widths+jobs)),hold,seeds[0],short_deadline,actions,stats[0],6,false,20.,-3.)) {
                State current=state;std::memcpy(trace,current.v,88);
                for(int tick=1;tick<nt;tick++) {
                    State following;step(current,int(actions[tick-1]),world.row(tick),world.platform(tick),np,following,world.axes(tick),world.platform_index(tick));
                    current=following;std::memcpy(trace+tick*11,current.v,88);
                }
                last_macro_width=std::min(16,*std::max_element(widths,widths+jobs));
                *controller_delay=1000+hold;stats[0].reached=nt-1;stats[0].status=1;return 0;
            }
        }
        // One-path replay and successful cheap controllers do not amortize a
        // whole spatial grid. Build it only for a real frontier expansion.
        {
            const auto index_began=Clock::now();
            {CpuAccounting index_cpu(stats[0]);stats[0].cpu_nanoseconds+=prepare_collision_cells(world,workers);}
            const auto elapsed=Clock::now()-index_began;deadline+=elapsed;
            last_index_seconds+=std::chrono::duration<double>(elapsed).count();
            last_index_bytes=world.collision_frames.size()*sizeof(FrameCollisionIndex)+world.collision_quads.size()*sizeof(CachedQuad)+
                world.collision_cells.size()+world.collision_offsets.size()*4+world.collision_members.size()*4+world.gravity_axes.size()*16+world.platform_index_bytes();
        }
        if(!world.fewest && !world.goal && requested_macro_width>16) {
            struct MacroJob {int width,hold;double cell,mode;};
            std::vector<MacroJob> trials;
            const std::vector<MacroJob> portfolio=nt>=2000
                ?std::vector<MacroJob>{{64,4,20.,-1.},{128,6,20.,-1.},{64,4,20.,-3.},{128,3,10.,-3.},
                    {512,4,5.,-4.},{256,3,10.,-1.},{512,3,5.,0.},{1024,4,5.,0.}}
                :std::vector<MacroJob>{{64,4,20.,-1.},{64,4,20.,-3.},{128,3,10.,-3.},{512,4,5.,-4.},
                    {256,3,10.,-1.},{128,6,20.,-1.},{512,3,5.,0.},{1024,4,5.,0.}};
            for(const MacroJob job:portfolio) {
                MacroJob trial=job;trial.width=std::min(trial.width,requested_macro_width);
                bool duplicate=false;
                for(const auto& prior:trials)if(prior.width==trial.width && prior.hold==trial.hold && prior.cell==trial.cell && prior.mode==trial.mode)duplicate=true;
                if(!duplicate)trials.push_back(trial);
            }
            std::atomic<int> next_trial{0},successful{-1};std::atomic<bool> stop{false},macro_failed{false};
            std::vector<std::atomic<bool>> cancelled(trials.size());
            for(auto& flag:cancelled)flag.store(false);
            std::vector<Stats> trial_stats(trials.size());
            std::vector<std::vector<int64_t>> trial_words(trials.size());
            const int runners=std::min(workers,int(trials.size()));last_portfolio_workers=runners;
            auto run_macro=[&]() {
                try {
                while(!stop.load(std::memory_order_relaxed)) {
                    const int index=next_trial.fetch_add(1);if(index>=int(trials.size()))break;
                    const int previous=successful.load();
                    if(previous>=0 && (world.race || index>previous))break;
                    const auto& trial=trials[index];trial_words[index].resize(nt-1);
                    if(macro_probe(world,state,trial.width,trial.hold,seeds[0],deadline,trial_words[index].data(),
                            trial_stats[index],0,false,trial.cell,trial.mode,world.race?&stop:&cancelled[index])) {
                        if(world.race) {
                            int expected=-1;
                            if(successful.compare_exchange_strong(expected,index))stop.store(true,std::memory_order_relaxed);
                        } else {
                            // A rolling window requests an ordered portfolio:
                            // a faster low-priority route must not cancel an
                            // earlier policy and make future windows depend
                            // on operating-system thread scheduling.
                            int best=successful.load();
                            while((best<0 || index<best) && !successful.compare_exchange_weak(best,index)){}
                            const int winner=successful.load();
                            for(int other=winner+1;other<int(trials.size());other++)cancelled[other].store(true,std::memory_order_relaxed);
                        }
                    }
                }
                }catch(...){macro_failed.store(true);stop.store(true);for(auto& flag:cancelled)flag.store(true);}
            };
            std::vector<std::thread> threads;JoinThreads joiner{threads};
            for(int runner=1;runner<runners;runner++)threads.emplace_back(run_macro);
            run_macro();for(auto& thread:threads)thread.join();
            if(macro_failed.load())return -3;
            uint64_t macro_workspace=0;
            for(const auto& trial:trial_stats) {
                stats[0].expanded+=trial.expanded;stats[0].generated+=trial.generated;stats[0].unique+=trial.unique;
                stats[0].discarded+=trial.discarded;stats[0].preview_steps+=trial.preview_steps;
                stats[0].cpu_nanoseconds+=trial.cpu_nanoseconds;stats[0].reached=std::max(stats[0].reached,trial.reached);
                macro_workspace+=trial.workspace_bytes;
            }
            for(const auto& trial:trial_words)macro_workspace+=trial.capacity()*sizeof(int64_t);
            stats[0].workspace_bytes=std::max(stats[0].workspace_bytes,macro_workspace);
            const int index=successful.load();
            if(index>=0) {
                    std::copy_n(trial_words[index].data(),nt-1,actions);
                    State current=state;std::memcpy(trace,current.v,88);
                    for(int tick=1;tick<nt;tick++) {
                        State following;step(current,int(actions[tick-1]),world.row(tick),world.platform(tick),np,following,world.axes(tick),world.platform_index(tick));
                        current=following;std::memcpy(trace+tick*11,current.v,88);
                    }
                    last_macro_width=trials[index].width;*controller_delay=2000+trials[index].hold;stats[0].reached=nt-1;stats[0].status=1;return 0;
            }
        }
        std::atomic<int> best(jobs);std::atomic<bool> failed(false);
        SpareWorkers pool(workers,0);last_portfolio_workers=1;
        const int word_stride=std::max(1,nt-1);
        std::vector<int64_t> words(size_t(jobs)*word_stride);
        auto group=[&](int begin,int end) {
            const int runners=std::min(workers,end-begin);if(runners<=0)return;
            pool.available.fetch_sub(runners);last_portfolio_workers=std::max(last_portfolio_workers,runners);
            std::atomic<int> next(begin);
            auto work=[&](){struct ReleaseRunner {SpareWorkers& pool;~ReleaseRunner(){pool.available.fetch_add(1);}} release{pool};
                try {while(true){int job=next.fetch_add(1);if(job>=end || (!world.fewest && (world.race?best.load()<jobs:job>best.load())))break;
                    probe(world,state,controls,counts,stride,widths[job],seeds[job],job,best,deadline,
                        words.data()+size_t(job)*word_stride,stats[job],pool);}}
                catch(...){failed.store(true);}
            };
            std::vector<std::thread> threads;JoinThreads joiner{threads};
            for(int i=1;i<runners;i++)threads.emplace_back(work);
            work();for(auto& thread:threads)thread.join();
        };
        // Give primary probes spare slots instead of competing immediately
        // with five expensive speculative previews. If all primaries fail,
        // the remaining styles share the original request deadline.
        const int primaries=std::min(3,jobs);
        if(*std::max_element(widths,widths+jobs)<512)group(0,jobs);
        else {
            group(0,primaries);
            if((world.fewest || best.load()>=jobs) && !failed.load())group(primaries,jobs);
        }
        last_edge_workers=pool.peak.load();last_hash_rebuilds=pool.hash_rebuilds.load();
        if(failed.load())return -3;
        int winner=best.load();if(winner>=jobs)return -1;
        if(world.fewest) {
            auto route_cost=[&](int job){int cost=0,previous=int(state.v[4]);
                for(int tick=0;tick<nt-1;tick++){int mask=int(words[size_t(job)*word_stride+tick]);cost+=(mask!=previous?world.operation_weight:0)+(mask?world.held_weight:0);previous=mask;}
                return cost;};
            int cheapest=route_cost(winner);
            for(int job=0;job<jobs;job++)if(stats[job].status==1){int cost=route_cost(job);if(cost<cheapest || (cost==cheapest && job<winner)){winner=job;cheapest=cost;}}
        }
        CpuAccounting replay_cpu(stats[winner]);
        std::copy_n(words.data()+size_t(winner)*word_stride,nt-1,actions);
        std::memcpy(trace,state.v,88);
        for(int tick=1;tick<nt;tick++){State out;step(state,int(actions[tick-1]),world.row(tick),world.platform(tick),np,out,world.axes(tick),world.platform_index(tick));state=out;std::memcpy(trace+tick*11,state.v,88);}
        return winner;
    }catch(...){return -3;}
}
// Event-free source ticks only: preserve each individual binary64 addition.
// The caller excludes callbacks, dialogue, arena movement, stabs and reversals.
int nohit_idle_world(double* rows,int count,double* blasters,int blaster_count,
    double* platforms,int platform_count,int platform_capacity,const double* dt,int limit,
    double delay,double* elapsed,double* boxes,double* polygons,double* platform_frames,int32_t* sizes) {
    const int stride=count*4,polygon_stride=blaster_count*8;
    int tick=0;
    while(tick<limit && *elapsed<delay) {
        count=nohit_bones_advance(rows,count,dt[tick]);
        for(int index=0;index<platform_count;++index) {
            auto at=[&](int column)->double& {return platforms[index+column*platform_capacity];};
            const bool born=at(7)!=0.;
            at(9)=born?0.:1.;at(10)=at(5);
            if(!born){at(0)+=at(4)*dt[tick];at(1)+=at(5)*dt[tick];}
            at(7)=0.;
            double* out=platform_frames+(tick*platform_count+index)*9;
            for(int column=0;column<6;++column)out[column]=at(column);
            out[6]=1.;out[7]=at(9);out[8]=at(10);
        }
        int32_t polygon_count=0;
        blaster_count=nohit_blasters_advance(blasters,blaster_count,dt[tick],
            polygons+tick*polygon_stride,&polygon_count);
        const int white=nohit_bones_geometry(rows,count,boxes+tick*stride);
        sizes[tick*4]=count;sizes[tick*4+1]=white;
        sizes[tick*4+2]=blaster_count;sizes[tick*4+3]=polygon_count;
        *elapsed+=dt[tick];
        ++tick;
    }
    return tick;
}

int nohit_search_goal(const double* initial,const double* env,int nt,const double* platforms,int np,
    const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,
    const int64_t* controls,const int64_t* counts,int stride,const int32_t* widths,
    const uint32_t* seeds,int jobs,int workers,double seconds,int64_t* actions,
    double* trace,Stats* stats,int32_t* controller_delay,const double* goal) {
    struct Reset {~Reset(){requested_goal=nullptr;}} reset;
    requested_goal=goal;
    return nohit_search(initial,env,nt,platforms,np,white,nw,blue,nb,polygons,nq,
        controls,counts,stride,widths,seeds,jobs,workers,seconds,actions,trace,stats,controller_delay);
}

int nohit_search_progress(const double* initial,const double* env,int nt,const double* platforms,int np,
    const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,
    const int64_t* controls,const int64_t* counts,int stride,const int32_t* widths,
    const uint32_t* seeds,int jobs,int workers,double seconds,int64_t* actions,
    double* trace,Stats* stats,int32_t* controller_delay,const double* goal,
    ProgressCallback callback,void* context) {
    struct Reset {const double* goal;const NativeProgress* progress;
        ~Reset(){requested_goal=goal;requested_progress=progress;}} reset{requested_goal,requested_progress};
    NativeProgress progress{callback,context};requested_goal=goal;requested_progress=&progress;
    return nohit_search(initial,env,nt,platforms,np,white,nw,blue,nb,polygons,nq,
        controls,counts,stride,widths,seeds,jobs,workers,seconds,actions,trace,stats,controller_delay);
}

}
