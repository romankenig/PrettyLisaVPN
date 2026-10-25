package com.prettylisavpn.android

import com.prettylisavpn.engine.TunnelDns
import org.junit.Assert.*
import org.junit.Test

class TunnelDnsTest {
    @Test fun validatesTransactionQuestionFlagsAndBoundedAnswerRecords() {
        val query=TunnelDns.query(0x1234)
        val reply=query.copyOf().apply {this[2]=0x81.toByte();this[3]=0x80.toByte();this[7]=1} +
            byteArrayOf(0xc0.toByte(),12,0,1,0,1,0,0,0,30,0,4,203.toByte(),0,113,5)
        assertEquals("203.0.113.5",TunnelDns.answers(reply,query).single().hostAddress)
        val cases=listOf(reply.copyOf(11),reply.copyOf(reply.size-1),reply.copyOf().apply {this[0]=0},reply.copyOf().apply {this[3]=0x83.toByte()},reply.copyOf().apply {this[2]=0x83.toByte()},reply.copyOf().apply {this[13]=0},reply.copyOf().apply {this[size-4]=127},reply.copyOf().apply {this[7]=33})
        for(bad in cases) {try {TunnelDns.answers(bad,query);fail("unsafe DNS reply accepted")} catch(_:IllegalArgumentException) {}}
    }
}
