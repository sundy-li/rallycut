//go:build windows

package childproc

import (
	"sync"
	"syscall"
	"unsafe"
)

// A kill-on-close job object keeps every helper (Python worker, FFmpeg,
// FFprobe, PowerShell picker, WebView2) inside the app's lifetime. Without it,
// ending RallyCut from Task Manager — or a crash — left the analysis worker
// running on a full core for the rest of the video. The app itself joins the
// job: when the process exits, Windows closes the handle and terminates every
// process that inherited membership.
const (
	jobObjectExtendedLimitInformation = 9
	jobObjectLimitKillOnJobClose      = 0x2000
)

type jobObjectBasicLimitInformation struct {
	PerProcessUserTimeLimit int64
	PerJobUserTimeLimit     int64
	LimitFlags              uint32
	MinimumWorkingSetSize   uintptr
	MaximumWorkingSetSize   uintptr
	ActiveProcessLimit      uint32
	Affinity                uintptr
	PriorityClass           uint32
	SchedulingClass         uint32
}

type jobObjectIOCounters struct {
	ReadOperationCount  uint64
	WriteOperationCount uint64
	OtherOperationCount uint64
	ReadTransferCount   uint64
	WriteTransferCount  uint64
	OtherTransferCount  uint64
}

type jobObjectExtendedLimitInformationStruct struct {
	BasicLimitInformation jobObjectBasicLimitInformation
	IOInfo                jobObjectIOCounters
	ProcessMemoryLimit    uintptr
	JobMemoryLimit        uintptr
	PeakProcessMemoryUsed uintptr
	PeakJobMemoryUsed     uintptr
}

var (
	jobOnce   sync.Once
	jobErr    error
	jobHandle syscall.Handle
	kernel32  = syscall.NewLazyDLL("kernel32.dll")

	procCreateJobObjectW         = kernel32.NewProc("CreateJobObjectW")
	procSetInformationJobObject  = kernel32.NewProc("SetInformationJobObject")
	procAssignProcessToJobObject = kernel32.NewProc("AssignProcessToJobObject")
	procGetCurrentProcess        = kernel32.NewProc("GetCurrentProcess")
)

// Init assigns the current process to a kill-on-close job. Call once before
// spawning helpers. Failure is reported to the caller and must not stop the
// app: running without the job only loses orphan cleanup.
func Init() error {
	jobOnce.Do(func() {
		handle, _, callErr := procCreateJobObjectW.Call(0, 0)
		if handle == 0 {
			jobErr = callErr
			return
		}
		var info jobObjectExtendedLimitInformationStruct
		info.BasicLimitInformation.LimitFlags = jobObjectLimitKillOnJobClose
		ok, _, setErr := procSetInformationJobObject.Call(
			handle, jobObjectExtendedLimitInformation,
			uintptr(unsafe.Pointer(&info)), unsafe.Sizeof(info))
		if ok == 0 {
			jobErr = setErr
			_ = syscall.CloseHandle(syscall.Handle(handle))
			return
		}
		process, _, _ := procGetCurrentProcess.Call()
		ok, _, assignErr := procAssignProcessToJobObject.Call(handle, process)
		if ok == 0 {
			jobErr = assignErr
			_ = syscall.CloseHandle(syscall.Handle(handle))
			return
		}
		jobHandle = syscall.Handle(handle)
	})
	return jobErr
}
