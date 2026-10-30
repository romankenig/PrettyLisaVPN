// SPDX-License-Identifier: MIT
package managed

import (
	"context"
	"io"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/xtls/xray-core/common/buf"
	"github.com/xtls/xray-core/transport/internet/grpc/encoding"
)

type blockedStream struct {
	ctx             context.Context
	started         chan struct{}
	once            sync.Once
	sending         atomic.Bool
	concurrentClose atomic.Bool
}

func (s *blockedStream) Context() context.Context { return s.ctx }
func (s *blockedStream) SendMsg(any) error        { return nil }
func (s *blockedStream) RecvMsg(any) error        { return io.EOF }
func (s *blockedStream) CloseSend() error {
	if s.sending.Load() {
		s.concurrentClose.Store(true)
	}
	return nil
}
func (s *blockedStream) block() error {
	s.sending.Store(true)
	s.once.Do(func() { close(s.started) })
	<-s.ctx.Done()
	s.sending.Store(false)
	return s.ctx.Err()
}

type singleStream struct{ *blockedStream }

func (s singleStream) Send(*encoding.Hunk) error     { return s.block() }
func (s singleStream) Recv() (*encoding.Hunk, error) { return nil, io.EOF }

type multiStream struct{ *blockedStream }

func (s multiStream) Send(*encoding.MultiHunk) error     { return s.block() }
func (s multiStream) Recv() (*encoding.MultiHunk, error) { return nil, io.EOF }

func TestGRPCCloseCancelsBlockedSendBeforeCloseSend(t *testing.T) {
	for _, multi := range []bool{false, true} {
		t.Run(map[bool]string{false: "single", true: "multi"}[multi], func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			s := &blockedStream{ctx: ctx, started: make(chan struct{})}
			var write func() error
			var closeStream func() error
			if multi {
				conn := encoding.NewMultiHunkReadWriter(multiStream{s}, cancel)
				closeStream = conn.Close
				write = func() error { b := buf.New(); b.WriteString("test"); return conn.WriteMultiBuffer(buf.MultiBuffer{b}) }
			} else {
				conn := encoding.NewHunkReadWriter(singleStream{s}, cancel)
				closeStream = conn.Close
				write = func() error { _, err := conn.Write([]byte("test")); return err }
			}
			done := make(chan error, 1)
			go func() { done <- write() }()
			select {
			case <-s.started:
			case <-time.After(time.Second):
				t.Fatal("send did not start")
			}
			closed := make(chan struct{})
			go func() { _ = closeStream(); close(closed) }()
			select {
			case <-closed:
			case <-time.After(time.Second):
				t.Fatal("close blocked on send")
			}
			if err := <-done; err == nil {
				t.Fatal("cancelled send succeeded")
			}
			if s.concurrentClose.Load() {
				t.Fatal("CloseSend raced with Send")
			}
			if err := write(); err == nil {
				t.Fatal("closed stream accepted a write")
			}
			_ = closeStream()
		})
	}
}
